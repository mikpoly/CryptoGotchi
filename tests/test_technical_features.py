from __future__ import annotations

import json
import time

from cryptogotchi.market_sessions import describe_market_session
from cryptogotchi.technical_analysis import analyze_market, compare_analyses


def _build_samples(now: int, *, breakout: bool = False) -> list[dict[str, float | int]]:
    samples = []
    base = 100.0
    count = 72 * 12  # 72 hours, one point every five minutes.
    for index in range(count):
        cycle = ((index % 48) - 24) * 0.025
        trend = index * 0.002
        price = base + cycle + trend
        if breakout and index >= count - 3:
            price += 5.0
        samples.append({"ts": now - (count - 1 - index) * 300, "price": price, "volume": 1000 + index})
    return samples


def test_analysis_uses_only_15m_1h_4h_and_is_json_safe():
    now = int(time.time())
    samples = _build_samples(now)
    market = {
        "id": "bitcoin",
        "symbol": "BTC",
        "name": "Bitcoin",
        "price": samples[-1]["price"],
        "fiat": "EUR",
        "metrics": {"15m": 0.4, "1h": 0.9, "24h": 3.4},
    }
    analysis = analyze_market(market, samples, now, "fr")
    assert set(analysis["timeframes"]) == {"15m", "1h", "4h"}
    assert analysis["verdict"] in {"buy", "sell", "wait"}
    assert analysis["disclaimer"].startswith("Avis simulé")
    for timeframe in ("15m", "1h", "4h"):
        frame = analysis["timeframes"][timeframe]
        assert frame["bias"] in {"buy", "sell", "wait"}
        assert "support_text" in frame
        assert "resistance_text" in frame
    json.dumps(analysis, ensure_ascii=False)


def test_breakout_is_detected_from_previous_candles():
    now = int(time.time())
    samples = _build_samples(now, breakout=True)
    market = {
        "id": "bitcoin",
        "symbol": "BTC",
        "name": "Bitcoin",
        "price": samples[-1]["price"],
        "fiat": "EUR",
        "metrics": {},
    }
    analysis = analyze_market(market, samples, now, "fr")
    assert any(
        frame["regime_code"] == "breakout_up"
        for frame in analysis["timeframes"].values()
    )


def test_compare_analyses_mentions_symbols():
    analyses = [
        {"symbol": "BTC", "verdict_label": "acheteur", "verdict_confidence": 75, "verdict_phrase": "Je suis acheteur."},
        {"symbol": "ETH", "verdict_label": "attente", "verdict_confidence": 55, "verdict_phrase": "J’attends."},
    ]
    text = compare_analyses(analyses, "fr")
    assert "BTC" in text and "ETH" in text


def test_describe_market_session_returns_local_schedule():
    info = describe_market_session({"symbol": "SPCX", "asset_kind": "tokenized_asset", "trading_mode": "market_session"}, "Europe/Brussels", "fr")
    assert info["market_name"]
    assert info["summary"]
    assert "status" in info
