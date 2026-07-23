from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .db import Database

WINDOWS = {"5m": 5 * 60, "15m": 15 * 60, "1h": 60 * 60}


@dataclass
class Metric:
    label: str
    change: float


class AlertEngine:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def pct_change(current: float, previous: float) -> float:
        if previous == 0:
            return 0.0
        return ((current - previous) / previous) * 100.0

    def metrics_for_coin(self, market: dict[str, Any], now: int) -> dict[str, Any]:
        """Calculate clean multi-window changes for one isolated stream.

        CoinGecko's provider-reported 1h change is authoritative when present.
        Local samples remain the source for 5m/15m and a diagnostic local 1h.
        This prevents a stale or contaminated chart point from creating a false
        1h threshold alert while still keeping short-window responsiveness.
        """
        provider_1h = market.get("change_1h")
        provider_24h = market.get("change_24h")
        metrics: dict[str, Any] = {
            "5m": None,
            "15m": None,
            "1h": float(provider_1h) if provider_1h is not None else None,
            "24h": float(provider_24h) if provider_24h is not None else None,
            "1h_source": "provider" if provider_1h is not None else "local",
            "quality_warning": "",
        }
        quote = str(market.get("fiat") or market.get("quote_currency") or "").lower()
        source = str(market.get("source") or "coingecko").lower()
        local_changes: dict[str, float | None] = {}
        for label, seconds in WINDOWS.items():
            tolerance = max(150, min(900, int(seconds * 0.55)))
            ref = self.db.reference_sample(
                market["id"], now - seconds, quote, source, max_age_seconds=tolerance
            )
            local = self.pct_change(float(market["price"]), float(ref["price"])) if ref else None
            local_changes[label] = local
            if label in {"5m", "15m"}:
                metrics[label] = local
        metrics["1h_local"] = local_changes.get("1h")
        if metrics["1h"] is None:
            metrics["1h"] = local_changes.get("1h")
        elif local_changes.get("1h") is not None:
            divergence = abs(float(metrics["1h"]) - float(local_changes["1h"]))
            allowed = max(1.5, abs(float(metrics["1h"])) * 0.75 + 0.75)
            if divergence > allowed:
                metrics["quality_warning"] = "local/provider 1h divergence"
        recent = self.db.samples_since(
            market["id"], now - 6 * 3600, exclude_latest=True,
            quote_currency=quote, source=source,
        )
        volumes = [float(x["volume"]) for x in recent if x.get("volume") and float(x["volume"]) > 0]
        avg_volume = sum(volumes) / len(volumes) if len(volumes) >= 4 else None
        metrics["volume_ratio"] = (float(market.get("volume") or 0) / avg_volume) if avg_volume else None
        return metrics

    def _make_alert(self, coin: dict[str, Any], rule: str, severity: str, message: str, now: int, metrics: dict[str, float | None]) -> dict[str, Any] | None:
        cooldown = max(1, int(coin.get("cooldown_minutes") or 30)) * 60
        key = f"{coin['id']}:{rule}"
        if self.db.recent_alert_exists(key, now - cooldown):
            return None
        return {
            "alert_key": key,
            "coin_id": coin["id"],
            "symbol": coin.get("symbol", coin["id"]).upper(),
            "rule": rule,
            "severity": severity,
            "message": message,
            "ts": now,
            "metrics": metrics,
            "social_post": bool(coin.get("social_post", False)),
        }

    @staticmethod
    def _price_text(price: float) -> str:
        if abs(price) >= 1000:
            return f"{price:,.2f}"
        if abs(price) >= 1:
            return f"{price:,.4f}".rstrip("0").rstrip(".")
        return f"{price:.8f}".rstrip("0").rstrip(".")

    def evaluate_coin(self, market: dict[str, Any], coin: dict[str, Any], now: int, language: str = "en") -> tuple[dict[str, float | None], list[dict[str, Any]]]:
        language = "fr" if language == "fr" else "en"
        metrics = self.metrics_for_coin(market, now)
        alerts: list[dict[str, Any]] = []
        if not coin.get("alerts_enabled", True):
            return metrics, alerts
        if market.get("is_stale") or market.get("market_status") == "closed" or market.get("data_quality") == "rejected":
            return metrics, alerts
        symbol = coin.get("symbol", market.get("symbol", market["id"])).upper()
        price = float(market["price"])
        fiat = str(market.get("fiat", "")).upper()
        price_text = self._price_text(price) + (f" {fiat}" if fiat else "")
        rise_sent = drop_sent = False
        for label in ("5m", "15m", "1h", "24h"):
            change = metrics.get(label)
            if change is None:
                continue
            rise = abs(float(coin.get(f"rise_{label}") or 0))
            drop = abs(float(coin.get(f"drop_{label}") or 0))
            if not rise_sent and rise > 0 and float(change) >= rise:
                severity = "high" if float(change) >= rise * 2 else "medium"
                message = (
                    f"🟢 {symbol} progresse de {float(change):+.2f} % en {label}. Prix observé : {price_text}."
                    if language == "fr" else
                    f"🟢 {symbol} rose {float(change):+.2f}% over {label}. Observed price: {price_text}."
                )
                alert = self._make_alert(coin, f"rise_{label}", severity, message, now, metrics)
                if alert:
                    alerts.append(alert); rise_sent = True
            if not drop_sent and drop > 0 and float(change) <= -drop:
                severity = "critical" if float(change) <= -drop * 2 else "high"
                message = (
                    f"🔴 {symbol} subit une chute de {float(change):.2f} % en {label}. Prix observé : {price_text}."
                    if language == "fr" else
                    f"🔴 {symbol} dropped {float(change):.2f}% over {label}. Observed price: {price_text}."
                )
                alert = self._make_alert(coin, f"drop_{label}", severity, message, now, metrics)
                if alert:
                    alerts.append(alert); drop_sent = True
        volume_ratio = metrics.get("volume_ratio")
        volume_threshold = abs(float(coin.get("volume_multiplier") or 0))
        if volume_ratio is not None and volume_threshold > 0 and float(volume_ratio) >= volume_threshold:
            message = (
                f"👀 Activité de volume inhabituelle sur {symbol} : ×{float(volume_ratio):.2f} par rapport à la moyenne récente."
                if language == "fr" else
                f"👀 Unusual volume activity on {symbol}: ×{float(volume_ratio):.2f} versus the recent average."
            )
            alert = self._make_alert(coin, "volume_spike", "medium", message, now, metrics)
            if alert:
                alerts.append(alert)
        previous = self.db.samples_since(
            coin["id"], now - 24 * 3600, exclude_latest=True,
            quote_currency=str(market.get("fiat") or "").lower(),
            source=str(market.get("source") or "coingecko").lower(),
        )
        previous_prices = [float(x["price"]) for x in previous]
        if len(previous_prices) >= 10:
            if coin.get("new_high_24h") and price > max(previous_prices):
                message = (
                    f"🚀 {symbol} inscrit un nouveau plus haut local sur 24 h à {price_text}."
                    if language == "fr" else
                    f"🚀 {symbol} set a new local 24h high at {price_text}."
                )
                alert = self._make_alert(coin, "new_high_24h", "medium", message, now, metrics)
                if alert:
                    alerts.append(alert)
            if coin.get("new_low_24h") and price < min(previous_prices):
                message = (
                    f"⚠️ {symbol} inscrit un nouveau plus bas local sur 24 h à {price_text}."
                    if language == "fr" else
                    f"⚠️ {symbol} set a new local 24h low at {price_text}."
                )
                alert = self._make_alert(coin, "new_low_24h", "high", message, now, metrics)
                if alert:
                    alerts.append(alert)
        return metrics, alerts

    def evaluate_market_breadth(self, evaluated: list[dict[str, Any]], rule_cfg: dict[str, Any], now: int, language: str = "en") -> list[dict[str, Any]]:
        if not rule_cfg.get("enabled", True):
            return []
        language = "fr" if language == "fr" else "en"
        label = f"{int(rule_cfg.get('breadth_window_minutes', 15))}m"
        if label not in ("5m", "15m"):
            label = "15m"
        cooldown = max(1, int(rule_cfg.get("cooldown_minutes", 45))) * 60
        results: list[dict[str, Any]] = []
        drop_threshold = abs(float(rule_cfg.get("breadth_drop_percent", 3.0)))
        drop_count = max(1, int(rule_cfg.get("breadth_count", 3)))
        eligible = [item for item in evaluated if item.get("coin", {}).get("include_in_market_mood", True) and not item.get("market", {}).get("is_stale") and item.get("market", {}).get("market_status") != "closed"]
        falling = [item for item in eligible if item["metrics"].get(label) is not None and float(item["metrics"][label]) <= -drop_threshold]
        drop_key = f"market:breadth_drop:{label}"
        if len(falling) >= drop_count and not self.db.recent_alert_exists(drop_key, now - cooldown):
            names = ", ".join(item["coin"].get("symbol", item["coin"]["id"]).upper() for item in falling[:6])
            message = (
                f"🚨 Baisse générale : {len(falling)} cryptos perdent au moins {drop_threshold:.1f} % en {label} ({names})."
                if language == "fr" else
                f"🚨 Broad drop: {len(falling)} cryptos lost at least {drop_threshold:.1f}% over {label} ({names})."
            )
            results.append({"alert_key": drop_key, "coin_id": None, "symbol": "MARKET", "rule": "market_breadth_drop", "severity": "critical", "message": message, "ts": now, "metrics": {"count": len(falling), "window": label, "threshold": drop_threshold}, "social_post": False})
        rise_threshold = abs(float(rule_cfg.get("breadth_rise_percent", 3.0)))
        rise_count = max(1, int(rule_cfg.get("breadth_rise_count", 3)))
        rising = [item for item in eligible if item["metrics"].get(label) is not None and float(item["metrics"][label]) >= rise_threshold]
        rise_key = f"market:breadth_rise:{label}"
        if len(rising) >= rise_count and not self.db.recent_alert_exists(rise_key, now - cooldown):
            names = ", ".join(item["coin"].get("symbol", item["coin"]["id"]).upper() for item in rising[:6])
            message = (
                f"🚀 Hausse générale : {len(rising)} cryptos gagnent au moins {rise_threshold:.1f} % en {label} ({names})."
                if language == "fr" else
                f"🚀 Broad rise: {len(rising)} cryptos gained at least {rise_threshold:.1f}% over {label} ({names})."
            )
            results.append({"alert_key": rise_key, "coin_id": None, "symbol": "MARKET", "rule": "market_breadth_rise", "severity": "high", "message": message, "ts": now, "metrics": {"count": len(rising), "window": label, "threshold": rise_threshold}, "social_post": False})
        return results
