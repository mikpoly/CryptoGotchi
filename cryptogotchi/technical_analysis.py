from __future__ import annotations

import hashlib
from typing import Any


TIMEFRAME_SPECS: dict[str, dict[str, int | str]] = {
    "15m": {"seconds": 15 * 60, "bucket": 15 * 60, "lookback": 12 * 3600},
    "1h": {"seconds": 60 * 60, "bucket": 60 * 60, "lookback": 48 * 3600},
    "4h": {"seconds": 4 * 3600, "bucket": 4 * 3600, "lookback": 72 * 3600},
}


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def format_price(value: float | None) -> str:
    if value is None:
        return "—"
    value = float(value)
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    if abs(value) >= 1:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _pct_change(current: float, previous: float | None) -> float | None:
    if previous in (None, 0):
        return None
    return (current - float(previous)) / float(previous) * 100.0


def _reference_price(samples: list[dict[str, Any]], target_ts: int, tolerance: int) -> float | None:
    best: tuple[int, float] | None = None
    for sample in samples:
        try:
            ts = int(sample["ts"])
            price = float(sample["price"])
        except (KeyError, TypeError, ValueError):
            continue
        distance = abs(ts - target_ts)
        if distance > tolerance:
            continue
        if best is None or distance < best[0]:
            best = (distance, price)
    return best[1] if best else None


def _build_candles(samples: list[dict[str, Any]], bucket_seconds: int, since_ts: int) -> list[dict[str, float | int]]:
    buckets: dict[int, dict[str, float | int]] = {}
    for sample in samples:
        try:
            ts = int(sample["ts"])
            price = float(sample["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if ts < since_ts or price <= 0:
            continue
        bucket_ts = ts - (ts % bucket_seconds)
        candle = buckets.get(bucket_ts)
        if candle is None:
            buckets[bucket_ts] = {
                "ts": bucket_ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "last_ts": ts,
            }
            continue
        candle["high"] = max(float(candle["high"]), price)
        candle["low"] = min(float(candle["low"]), price)
        if ts >= int(candle["last_ts"]):
            candle["close"] = price
            candle["last_ts"] = ts
    return [buckets[key] for key in sorted(buckets)]


def _ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    period = max(2, min(period, len(values)))
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _slope_percent(values: list[float], count: int = 4) -> float:
    if len(values) < 2:
        return 0.0
    window = values[-max(2, min(count, len(values))):]
    first = window[0]
    return ((window[-1] - first) / first * 100.0) if first else 0.0


def _trend(current: float, closes: list[float], language: str) -> tuple[str, str, int]:
    if len(closes) < 3:
        return (("neutral" if language == "en" else "neutre"), "neutral", 0)
    short = _ema(closes[-12:], 5)
    long = _ema(closes[-24:], 10)
    slope = _slope_percent(closes, 5)
    score = 0
    if short is not None:
        score += 1 if current > short else -1 if current < short else 0
    if short is not None and long is not None:
        score += 1 if short > long else -1 if short < long else 0
    threshold = 0.08
    score += 1 if slope > threshold else -1 if slope < -threshold else 0
    if score >= 2:
        return (("bullish" if language == "en" else "haussière"), "bullish", score)
    if score <= -2:
        return (("bearish" if language == "en" else "baissière"), "bearish", score)
    return (("neutral" if language == "en" else "neutre"), "neutral", score)


def _pivot_levels(candles: list[dict[str, float | int]]) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    if len(candles) < 3:
        return highs, lows
    for index in range(1, len(candles) - 1):
        previous = candles[index - 1]
        current = candles[index]
        following = candles[index + 1]
        current_high = float(current["high"])
        current_low = float(current["low"])
        if current_high >= float(previous["high"]) and current_high >= float(following["high"]):
            highs.append(current_high)
        if current_low <= float(previous["low"]) and current_low <= float(following["low"]):
            lows.append(current_low)
    return highs, lows


def _nearest_zone(levels: list[float], current: float, direction: str, tolerance_pct: float) -> dict[str, Any] | None:
    if direction == "support":
        eligible = [level for level in levels if level <= current]
        eligible.sort(reverse=True)
    else:
        eligible = [level for level in levels if level >= current]
        eligible.sort()
    if not eligible:
        return None
    seed = eligible[0]
    tolerance = max(abs(current) * tolerance_pct / 100.0, abs(seed) * tolerance_pct / 100.0, 1e-12)
    clustered = [level for level in eligible if abs(level - seed) <= tolerance]
    low = min(clustered)
    high = max(clustered)
    touches = len(clustered)
    confidence = max(40, min(92, 42 + touches * 12))
    return {
        "low": low,
        "high": high,
        "touches": touches,
        "confidence": confidence,
        "text": _zone_text_values(low, high),
    }


def _zone_text_values(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "—"
    if abs(high - low) <= max(1e-12, abs(high) * 0.0005):
        return format_price(high)
    return f"{format_price(low)}–{format_price(high)}"


def _position_in_range(current: float, support: dict[str, Any] | None, resistance: dict[str, Any] | None) -> int | None:
    if not support or not resistance:
        return None
    low = float(support["high"])
    high = float(resistance["low"])
    if high <= low:
        return None
    ratio = (current - low) / (high - low)
    return max(0, min(100, int(round(ratio * 100.0))))


def _regime(
    current: float,
    trend_code: str,
    support: dict[str, Any] | None,
    resistance: dict[str, Any] | None,
    language: str,
    margin_pct: float,
    prior_high: float | None = None,
    prior_low: float | None = None,
) -> tuple[str, str]:
    margin = abs(current) * margin_pct / 100.0
    if prior_high is not None and current > float(prior_high) + margin:
        return (("bullish breakout" if language == "en" else "cassure haussière"), "breakout_up")
    if prior_low is not None and current < float(prior_low) - margin:
        return (("bearish breakout" if language == "en" else "cassure baissière"), "breakout_down")
    if support and resistance:
        width = float(resistance["low"]) - float(support["high"])
        width_pct = width / current * 100.0 if current else 0.0
        if width > 0 and width_pct <= 8.0:
            return ("range", "range")
    if trend_code == "bullish":
        return (("up trend" if language == "en" else "tendance haussière"), "trend_up")
    if trend_code == "bearish":
        return (("down trend" if language == "en" else "tendance baissière"), "trend_down")
    return (("waiting zone" if language == "en" else "zone d’attente"), "neutral")


def _bias(
    trend_code: str,
    regime_code: str,
    position_pct: int | None,
    change: float | None,
    language: str,
    symbol: str,
    timeframe: str,
) -> tuple[str, str, int, str]:
    score = 0
    if regime_code == "breakout_up":
        score += 4
    elif regime_code == "breakout_down":
        score -= 4
    elif regime_code == "trend_up":
        score += 2
    elif regime_code == "trend_down":
        score -= 2
    if trend_code == "bullish":
        score += 1
    elif trend_code == "bearish":
        score -= 1
    if regime_code == "range" and position_pct is not None:
        if position_pct <= 25 and trend_code != "bearish":
            score += 1
        elif position_pct >= 75 and trend_code != "bullish":
            score -= 1
    if change is not None:
        score += 1 if change >= 0.8 else -1 if change <= -0.8 else 0
    if score >= 2:
        code = "buy"
        label = "buyer" if language == "en" else "acheteur"
    elif score <= -2:
        code = "sell"
        label = "seller" if language == "en" else "vendeur"
    else:
        code = "wait"
        label = "wait" if language == "en" else "attente"
    confidence = max(35, min(90, 45 + abs(score) * 10))
    phrase = _bias_phrase(code, language, symbol, timeframe)
    return code, label, confidence, phrase


def _bias_phrase(code: str, language: str, symbol: str, timeframe: str) -> str:
    choices = {
        "fr": {
            "buy": [
                "De mon côté, je suis plutôt acheteur ici, tant que le support tient.",
                "Le terrain me plaît : j’attendrais un repli propre puis je passerais plutôt à l’achat.",
                "Soyons un peu fous : mon biais est acheteur, mais je garde un œil sur le support.",
            ],
            "sell": [
                "Moi, je serais plutôt vendeur tant que le prix reste sous la résistance.",
                "La pression me paraît baissière : de mon côté, je privilégierais la vente.",
                "Je n’aime pas cette faiblesse ; mon biais serait vendeur pour le moment.",
            ],
            "wait": [
                "Je garde mes jetons dans ma poche : le signal n’est pas assez propre.",
                "Pas de précipitation, j’attendrais une cassure claire.",
                "Les unités de temps ne sont pas alignées ; moi, j’observerais encore.",
            ],
        },
        "en": {
            "buy": [
                "I would lean toward buying here while support still holds.",
                "I like the terrain: I would wait for a clean pullback, then lean long.",
                "Let’s be a little bold: my bias is bullish, but I am watching support.",
            ],
            "sell": [
                "I would lean toward selling while price stays below resistance.",
                "Pressure looks bearish to me, so I would favor the sell side.",
                "I do not like this weakness; my bias would be bearish for now.",
            ],
            "wait": [
                "I am keeping my coins in my pocket: the signal is not clean enough.",
                "No rush. I would wait for a clear break.",
                "The timeframes do not agree, so I would keep watching.",
            ],
        },
    }
    language = "fr" if language == "fr" else "en"
    pool = choices[language][code]
    digest = hashlib.sha256(f"{symbol}:{timeframe}:{code}".encode("utf-8")).digest()
    return pool[digest[0] % len(pool)]


def _freshness(age_seconds: int, language: str) -> str:
    if age_seconds <= 90:
        return "fresh" if language == "en" else "fraîches"
    if age_seconds <= 300:
        return "recent" if language == "en" else "récentes"
    return "delayed" if language == "en" else "retardées"


def _analyze_timeframe(
    samples: list[dict[str, Any]],
    current: float,
    now: int,
    timeframe: str,
    language: str,
    symbol: str,
) -> dict[str, Any]:
    spec = TIMEFRAME_SPECS[timeframe]
    seconds = int(spec["seconds"])
    bucket = int(spec["bucket"])
    lookback = int(spec["lookback"])
    candles = _build_candles(samples, bucket, now - lookback)
    closes = [float(candle["close"]) for candle in candles]
    historical = candles[:-1] if len(candles) > 1 else candles
    pivot_highs, pivot_lows = _pivot_levels(historical)
    if historical:
        recent = historical[-min(12, len(historical)):]
        pivot_highs.extend([max(float(candle["high"]) for candle in recent)])
        pivot_lows.extend([min(float(candle["low"]) for candle in recent)])
    tolerance = {"15m": 0.30, "1h": 0.45, "4h": 0.70}[timeframe]
    support = _nearest_zone(pivot_lows, current, "support", tolerance)
    resistance = _nearest_zone(pivot_highs, current, "resistance", tolerance)
    reference = _reference_price(samples, now - seconds, max(180, min(1800, int(seconds * 0.45))))
    change = _pct_change(current, reference)
    trend_label, trend_code, trend_score = _trend(current, closes, language)
    # Breakout reference excludes the current partial candle and, when
    # possible, the latest closed candle. This lets a fresh closed candle be
    # recognized as the breakout candle instead of becoming its own ceiling.
    breakout_history = historical[:-1] if len(historical) > 1 else historical
    prior_high = max((float(candle["high"]) for candle in breakout_history), default=None)
    prior_low = min((float(candle["low"]) for candle in breakout_history), default=None)
    regime_label, regime_code = _regime(
        current,
        trend_code,
        support,
        resistance,
        language,
        {"15m": 0.12, "1h": 0.18, "4h": 0.25}[timeframe],
        prior_high=prior_high,
        prior_low=prior_low,
    )
    # After a breakout, the broken historical level becomes the nearest
    # reference zone on the other side of price.
    if regime_code == "breakout_up" and support is None:
        support = _nearest_zone(pivot_highs, current, "support", tolerance)
    elif regime_code == "breakout_down" and resistance is None:
        resistance = _nearest_zone(pivot_lows, current, "resistance", tolerance)
    position = _position_in_range(current, support, resistance)
    bias_code, bias_label, confidence, phrase = _bias(
        trend_code, regime_code, position, change, language, symbol, timeframe
    )
    return {
        "timeframe": timeframe,
        "change": change,
        "trend": trend_label,
        "trend_code": trend_code,
        "trend_score": trend_score,
        "regime": regime_label,
        "regime_code": regime_code,
        "support": support,
        "resistance": resistance,
        "support_text": support["text"] if support else "—",
        "resistance_text": resistance["text"] if resistance else "—",
        "position_in_range_pct": position,
        "bias": bias_code,
        "bias_label": bias_label,
        "bias_confidence": confidence,
        "bias_phrase": phrase,
        "candle_count": len(candles),
        "ready": len(candles) >= 3,
    }


def _global_verdict(timeframes: dict[str, dict[str, Any]], language: str, symbol: str) -> tuple[str, str, int, str]:
    weights = {"15m": 1, "1h": 2, "4h": 3}
    score = 0
    ready_weight = 0
    for timeframe, weight in weights.items():
        item = timeframes[timeframe]
        if not item.get("ready"):
            continue
        ready_weight += weight
        score += weight if item.get("bias") == "buy" else -weight if item.get("bias") == "sell" else 0
    if ready_weight == 0:
        code = "wait"
    elif score >= 3:
        code = "buy"
    elif score <= -3:
        code = "sell"
    else:
        code = "wait"
    label = {
        "fr": {"buy": "acheteur", "sell": "vendeur", "wait": "attente"},
        "en": {"buy": "buyer", "sell": "seller", "wait": "wait"},
    }[language][code]
    confidence = max(35, min(92, 45 + abs(score) * 7))
    aligned = timeframes["1h"].get("bias") == timeframes["4h"].get("bias") == code
    if language == "fr":
        if code == "buy":
            phrase = (
                "De mon côté, je suis plutôt acheteur sur repli : le 1 h et le 4 h vont dans le même sens."
                if aligned else
                "Mon biais global reste acheteur, mais j’attendrais un point d’entrée près d’un support."
            )
        elif code == "sell":
            phrase = (
                "De mon côté, je suis plutôt vendeur sur rebond : le 1 h et le 4 h restent fragiles."
                if aligned else
                "Mon biais global reste vendeur, mais je ne poursuivrais pas une chute déjà avancée."
            )
        else:
            phrase = "Je reste en attente : les unités 15 min, 1 h et 4 h ne racontent pas encore la même histoire."
    else:
        if code == "buy":
            phrase = (
                "I lean bullish on a pullback: the 1h and 4h views agree."
                if aligned else
                "My overall bias is bullish, but I would wait for an entry near support."
            )
        elif code == "sell":
            phrase = (
                "I lean bearish on a bounce: the 1h and 4h views remain fragile."
                if aligned else
                "My overall bias is bearish, but I would not chase an extended drop."
            )
        else:
            phrase = "I would wait: the 15m, 1h and 4h views are not telling the same story yet."
    return code, label, confidence, phrase


def analyze_market(
    market: dict[str, Any],
    samples: list[dict[str, Any]],
    now: int,
    language: str = "en",
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    language = "fr" if language == "fr" else "en"
    cleaned: list[dict[str, Any]] = []
    for sample in samples:
        try:
            ts = int(sample["ts"])
            price = float(sample["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if price > 0:
            cleaned.append({"ts": ts, "price": price})
    cleaned.sort(key=lambda item: item["ts"])
    current = _safe_float(market.get("price")) or (float(cleaned[-1]["price"]) if cleaned else 0.0)
    symbol = str(market.get("symbol") or market.get("id") or "?").upper()
    fiat = str(market.get("fiat") or "").upper()
    latest_ts = int(cleaned[-1]["ts"]) if cleaned else now
    age = max(0, now - latest_ts)
    timeframes = {
        name: _analyze_timeframe(cleaned, current, now, name, language, symbol)
        for name in ("15m", "1h", "4h")
    }
    verdict, verdict_label, verdict_confidence, verdict_phrase = _global_verdict(timeframes, language, symbol)
    reference = timeframes["1h"] if timeframes["1h"].get("ready") else timeframes["15m"]
    if language == "fr":
        summary = (
            f"{symbol} — biais {verdict_label}. 15 min : {timeframes['15m']['bias_label']}; "
            f"1 h : {timeframes['1h']['bias_label']}; 4 h : {timeframes['4h']['bias_label']}."
        )
    else:
        summary = (
            f"{symbol} — {verdict_label} bias. 15m: {timeframes['15m']['bias_label']}; "
            f"1h: {timeframes['1h']['bias_label']}; 4h: {timeframes['4h']['bias_label']}."
        )
    return {
        "symbol": symbol,
        "name": market.get("name") or symbol,
        "price": current,
        "fiat": fiat,
        "timeframes": timeframes,
        "change_15m": timeframes["15m"].get("change"),
        "change_1h": timeframes["1h"].get("change"),
        "change_4h": timeframes["4h"].get("change"),
        "trend": reference.get("trend"),
        "regime": reference.get("regime"),
        "regime_code": reference.get("regime_code"),
        "support_zone": reference.get("support"),
        "resistance_zone": reference.get("resistance"),
        "support_text": reference.get("support_text", "—"),
        "resistance_text": reference.get("resistance_text", "—"),
        "verdict": verdict,
        "verdict_label": verdict_label,
        "verdict_confidence": verdict_confidence,
        "verdict_phrase": verdict_phrase,
        "summary": summary,
        "detailed_message": verdict_phrase,
        "freshness": _freshness(age, language),
        "last_sample_age_seconds": age,
        "samples_count": len(cleaned),
        "session": session or {},
        "disclaimer": (
            "Avis simulé du compagnon — pas un conseil financier."
            if language == "fr" else
            "Simulated companion opinion — not financial advice."
        ),
    }


def compare_analyses(analyses: list[dict[str, Any]], language: str = "en") -> str:
    language = "fr" if language == "fr" else "en"
    if not analyses:
        return "Aucun actif disponible." if language == "fr" else "No asset is available."
    if len(analyses) == 1:
        item = analyses[0]
        return f"{item['symbol']} : {item['verdict_phrase']}"
    labels = ", ".join(f"{item['symbol']} {item['verdict_label']}" for item in analyses)
    conviction = sorted(analyses, key=lambda item: int(item.get("verdict_confidence", 0)), reverse=True)
    clearest = conviction[0]
    if language == "fr":
        return (
            f"Comparaison simple — {labels}. Le signal le plus net est {clearest['symbol']} : "
            f"{clearest['verdict_phrase']}"
        )
    return (
        f"Simple comparison — {labels}. The clearest signal is {clearest['symbol']}: "
        f"{clearest['verdict_phrase']}"
    )
