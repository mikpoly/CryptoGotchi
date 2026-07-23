from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__
from .ai_clients import NarrativeAI
from .alerts import AlertEngine
from .config import ConfigManager, asset_data_note
from .connectivity import active_connection_info, economy_state
from .db import Database
from .display import DisplayManager
from .notifiers import NotifierHub
from .personality import MicroBrain, choose_state, state_message
from .ranking import RankingClient
from .system_info import collect_system_info
from .technical_analysis import analyze_market, compare_analyses
from .market_sessions import describe_market_session

log = logging.getLogger(__name__)
VERSION = __version__
HARD_MAX_ACTIVE_ASSETS = 100


class CoinGeckoProvider:
    def __init__(self, config: dict[str, Any]):
        self.session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=2,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self._transfer_bytes = 0
        self._transfer_requests = 0
        self.update_config(config)

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        provider = config["provider"]
        self.base_url = provider.get("base_url", "https://api.coingecko.com/api/v3").rstrip("/")
        self.timeout = max(5, int(provider.get("timeout_seconds", 15)))
        self.api_key = provider.get("api_key", "")
        self.freshness_seconds = max(120, int(provider.get("freshness_seconds", 600)))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": f"CryptoGotchi-by-mikpoly/{VERSION}"}
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key
        return headers

    def _get(self, path: str, params: dict[str, Any]) -> requests.Response:
        response = self.session.get(
            f"{self.base_url}{path}",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        # Le corps est déjà chargé par requests; sa longueur est une bonne estimation
        # de la consommation API (hors en-têtes TLS/IP).
        self._transfer_bytes += len(response.content or b"")
        self._transfer_requests += 1
        response.raise_for_status()
        return response

    def consume_transfer_stats(self) -> dict[str, int]:
        stats = {"bytes": self._transfer_bytes, "requests": self._transfer_requests}
        self._transfer_bytes = 0
        self._transfer_requests = 0
        return stats

    @staticmethod
    def _iso_timestamp(value: Any) -> int | None:
        if not value:
            return None
        try:
            return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
        except (TypeError, ValueError):
            return None

    def fetch_markets(self, coin_ids: list[str], fiat: str) -> list[dict[str, Any]]:
        """Fetch market rows in bounded batches.

        CoinGecko accepts up to 250 rows per page, but CryptoGotchi deliberately
        caps active assets at 100 on the Pi Zero 2 W. Batching remains here so a
        custom compatible provider cannot silently truncate a future request.
        """
        ids = list(dict.fromkeys(str(item).strip().lower() for item in coin_ids if str(item).strip()))
        if not ids:
            return []
        result: list[dict[str, Any]] = []
        for start in range(0, len(ids), 250):
            batch = ids[start:start + 250]
            response = self._get(
                "/coins/markets",
                {
                    "vs_currency": fiat,
                    "ids": ",".join(batch),
                    "price_change_percentage": "1h,24h",
                    "sparkline": "false",
                    "precision": "full",
                    "per_page": min(250, max(1, len(batch))),
                    "page": 1,
                },
            )
            for row in response.json():
                current_price = row.get("current_price")
                if current_price is None:
                    continue
                updated_ts = self._iso_timestamp(row.get("last_updated"))
                age = max(0, int(time.time()) - updated_ts) if updated_ts else None
                result.append({
                    "id": row["id"],
                    "symbol": str(row.get("symbol", row["id"])).upper(),
                    "name": row.get("name", row["id"]),
                    "price": float(current_price),
                    "volume": float(row.get("total_volume") or 0),
                    "market_cap": float(row.get("market_cap") or 0),
                    "change_1h": row.get("price_change_percentage_1h_in_currency"),
                    "change_24h": row.get("price_change_percentage_24h_in_currency", row.get("price_change_percentage_24h")),
                    "high_24h": row.get("high_24h"),
                    "low_24h": row.get("low_24h"),
                    "last_updated": row.get("last_updated"),
                    "last_updated_ts": updated_ts,
                    "data_age_seconds": age,
                    "is_stale": age is not None and age > self.freshness_seconds,
                    "market_status": "stale" if age is not None and age > self.freshness_seconds else "open",
                    "source": "coingecko",
                    "fiat": fiat,
                })
        return result

    def fetch_history(self, coin_id: str, fiat: str, days: int = 1) -> list[dict[str, Any]]:
        response = self._get(
            f"/coins/{coin_id}/market_chart",
            {"vs_currency": fiat, "days": max(1, min(2, int(days))), "precision": "full"},
        )
        payload = response.json()
        prices = payload.get("prices") or []
        volumes = payload.get("total_volumes") or []
        volume_by_ts: dict[int, float] = {}
        for point in volumes:
            if not isinstance(point, list) or len(point) < 2:
                continue
            try:
                volume_by_ts[int(float(point[0]) / 1000)] = float(point[1])
            except (TypeError, ValueError):
                continue
        history: list[dict[str, Any]] = []
        for point in prices:
            if not isinstance(point, list) or len(point) < 2:
                continue
            try:
                ts = int(float(point[0]) / 1000)
                price = float(point[1])
            except (TypeError, ValueError):
                continue
            # Les timestamps volume/prix peuvent différer de quelques secondes.
            volume = volume_by_ts.get(ts)
            if volume is None and volume_by_ts:
                nearest = min(volume_by_ts, key=lambda candidate: abs(candidate - ts))
                if abs(nearest - ts) <= 180:
                    volume = volume_by_ts[nearest]
            history.append({"ts": ts, "price": price, "volume": volume, "change_24h": None})
        return history

    def search(self, query: str) -> list[dict[str, Any]]:
        response = self._get("/search", {"query": query})
        results: list[dict[str, Any]] = []
        for item in response.json().get("coins", [])[:20]:
            name = str(item.get("name", item["id"]))
            coin_id = str(item["id"])
            symbol = str(item.get("symbol", "")).upper()
            lowered = f"{coin_id} {name}".lower()
            warning = ""
            kind = "crypto"
            if "robinhood token" in lowered or "tokenized stock" in lowered or "tokenized-stock" in lowered:
                kind = "tokenized_asset"
                warning = "24/7 tokenized asset — not the official exchange-listed share"
            elif symbol in {"XAU", "XAG", "XPT", "XPD"}:
                kind = "crypto_token"
                warning = f"Crypto token named {symbol} — not the spot metal"
            results.append({
                "id": coin_id,
                "name": name,
                "symbol": symbol,
                "market_cap_rank": item.get("market_cap_rank"),
                "thumb": item.get("thumb", ""),
                "asset_kind": kind,
                "warning": warning,
            })
        return results

    def inspect_coin(self, coin_id: str) -> dict[str, Any]:
        response = self._get(
            f"/coins/{coin_id}",
            {
                "localization": "false", "tickers": "false", "market_data": "false",
                "community_data": "false", "developer_data": "false", "sparkline": "false",
            },
        )
        item = response.json()
        name = str(item.get("name", coin_id))
        symbol = str(item.get("symbol", "")).upper()
        categories = [str(value) for value in (item.get("categories") or []) if value]
        haystack = " ".join([coin_id, name, *categories]).lower()
        asset_kind = "crypto"
        trading_mode = "24x7"
        note = ""
        include = True
        if any(token in haystack for token in ("tokenized stock", "stocks ecosystem", "robinhood chain stocks", "robinhood token")):
            asset_kind = "tokenized_asset"
            note = "Tokenized asset traded on crypto markets 24/7; it is not the official exchange-listed share."
            include = False
        elif symbol in {"XAU", "XAG", "XPT", "XPD"}:
            asset_kind = "crypto_token"
            note = f"This is a crypto token using the {symbol} ticker, not the spot metal price."
            include = False
        elif any("meme" in category.lower() for category in categories):
            asset_kind = "meme"
        return {
            "id": coin_id, "name": name, "symbol": symbol, "categories": categories[:12],
            "asset_kind": asset_kind, "trading_mode": trading_mode,
            "data_note": note, "include_in_market_mood": include,
        }


class GoldApiProvider:
    """Validated USD spot metals with optional reference FX conversion.

    Gold API's canonical free endpoint is /price/{SYMBOL} and returns USD per
    native unit. v0.5 incorrectly appended /USD, which can return a conversion
    shape rather than USD/oz and produced inverse-looking values. This provider
    always reads the canonical USD quote, validates it, then converts to the
    selected display currency through Frankfurter reference rates when needed.
    """

    USD_BOUNDS = {
        "XAU": (500.0, 10000.0),
        "XAG": (5.0, 500.0),
        "XPT": (100.0, 10000.0),
        "XPD": (100.0, 10000.0),
        "HG": (0.5, 100.0),
    }

    def __init__(self, config: dict[str, Any]):
        self.session = requests.Session()
        retry = Retry(
            total=3, connect=3, read=2, backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}), respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self._transfer_bytes = 0
        self._transfer_requests = 0
        self._fx_cache: dict[str, tuple[float, int, str]] = {}
        self.update_config(config)

    def update_config(self, config: dict[str, Any]) -> None:
        provider = config.get("provider", {})
        self.base_url = str(provider.get("gold_api_base_url", "https://api.gold-api.com")).rstrip("/")
        self.fx_base_url = str(provider.get("fx_api_base_url", "https://api.frankfurter.dev/v2")).rstrip("/")
        self.timeout = max(5, int(provider.get("timeout_seconds", 15)))
        self.freshness_seconds = max(120, int(provider.get("freshness_seconds", 600)))

    @staticmethod
    def _iso_timestamp(value: Any) -> int | None:
        if not value:
            return None
        try:
            return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _session_status(now: int) -> str:
        # Approximation of the global metals/FX week: Friday 22:00 UTC through
        # Sunday 22:00 UTC is marked closed. Broker sessions may differ.
        moment = datetime.fromtimestamp(now, timezone.utc)
        weekday, hour = moment.weekday(), moment.hour
        if weekday == 5 or (weekday == 6 and hour < 22) or (weekday == 4 and hour >= 22):
            return "closed"
        return "open"

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self.session.get(
            url,
            headers={"Accept": "application/json", "User-Agent": f"CryptoGotchi-by-mikpoly/{VERSION}"},
            timeout=self.timeout,
        )
        self._transfer_bytes += len(response.content or b"")
        self._transfer_requests += 1
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected provider payload")
        return payload

    def _fx_rate(self, quote: str, now: int) -> tuple[float, str]:
        quote = quote.upper()
        if quote == "USD":
            return 1.0, datetime.fromtimestamp(now, timezone.utc).date().isoformat()
        cached = self._fx_cache.get(quote)
        if cached and now - cached[1] < 6 * 3600:
            return cached[0], cached[2]
        payload = self._get_json(f"{self.fx_base_url}/rate/USD/{quote}")
        rate = float(payload.get("rate"))
        if not (rate > 0):
            raise ValueError(f"Invalid USD/{quote} reference rate")
        date = str(payload.get("date") or "")
        self._fx_cache[quote] = (rate, now, date)
        return rate, date

    @classmethod
    def _validate_usd_price(cls, symbol: str, price: float) -> None:
        low, high = cls.USD_BOUNDS.get(symbol, (0.000001, 1e12))
        if not (low <= price <= high):
            raise ValueError(
                f"Rejected implausible {symbol} USD quote {price:g}; expected {low:g}–{high:g}"
            )

    def fetch_markets(self, coins: list[dict[str, Any]], fiat: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        now = int(time.time())
        for coin in coins:
            symbol = str(coin.get("provider_symbol") or coin.get("symbol") or "XAU").upper()
            quote = str(coin.get("quote_currency") or fiat or "usd").upper()
            try:
                # Canonical endpoint: USD price per native unit, e.g. USD/oz for XAU.
                payload = self._get_json(f"{self.base_url}/price/{symbol}")
                raw_price = payload.get("price")
                if raw_price is None:
                    raise ValueError(f"Missing {symbol} price")
                usd_price = float(raw_price)
                self._validate_usd_price(symbol, usd_price)
                fx_rate, fx_date = self._fx_rate(quote, now)
                price = usd_price * fx_rate
                updated_ts = self._iso_timestamp(payload.get("updatedAt")) or now
                age = max(0, now - updated_ts)
                session = self._session_status(now)
                stale = age > self.freshness_seconds
                results.append({
                    "id": coin["id"],
                    "symbol": symbol,
                    "name": str(payload.get("name") or coin.get("name") or f"{symbol} Spot"),
                    "price": price,
                    "native_price_usd": usd_price,
                    "fx_rate": fx_rate,
                    "fx_rate_date": fx_date,
                    "volume": 0.0,
                    "market_cap": 0.0,
                    "change_1h": None,
                    "change_24h": None,
                    "last_updated": payload.get("updatedAt"),
                    "last_updated_ts": updated_ts,
                    "data_age_seconds": age,
                    "is_stale": stale,
                    "market_status": "stale" if stale else session,
                    "source": "gold_api",
                    "fiat": quote.lower(),
                    "unit": "pound" if symbol == "HG" else "troy_ounce",
                    "data_quality": "validated",
                })
            except (requests.RequestException, TypeError, ValueError) as exc:
                # One unavailable or malformed metal must not stop crypto prices.
                log.warning("Rejected %s market quote: %s", symbol, exc)
                continue
        return results

    def consume_transfer_stats(self) -> dict[str, int]:
        stats = {"bytes": self._transfer_bytes, "requests": self._transfer_requests}
        self._transfer_bytes = 0
        self._transfer_requests = 0
        return stats


class MarketWorker:
    def __init__(self, config: ConfigManager, db: Database):
        self.config_manager = config
        self.db = db
        self.alert_engine = AlertEngine(db)
        cfg = config.load()
        self.provider = CoinGeckoProvider(cfg)
        self.gold_provider = GoldApiProvider(cfg)
        self.notifiers = NotifierHub(config, db)
        self.ranking = RankingClient(config, db)
        # v0.5 could still inherit already-labelled but contaminated samples
        # from earlier installs. Rebuild only market-derived data once; user
        # configuration, credentials, XP and achievements are preserved.
        if not self.db.get_state("market_integrity_v6_clean_reset", False):
            self.db.clear_price_samples()
            self.db.clear_alerts()
            self.db.clear_journals()
            memory = self.db.get_state("companion_brain_v2", {})
            if isinstance(memory, dict):
                memory["daily"] = {}
                memory["recent"] = []
                memory["state"] = "offline"
                memory["state_streak"] = 0
                self.db.set_state("companion_brain_v2", memory)
            self.db.set_state("market_integrity_v6_clean_reset", True)
        self.display = DisplayManager(config)
        self.display.set_callbacks(
            self.force_refresh,
            self.toggle_notifications,
            self.ask_selected_coin,
            lambda: self.interact("pet"),
        )
        self.brain = MicroBrain(db)
        self.narrative_ai = NarrativeAI()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._status_lock = threading.RLock()
        self._backfill_lock = threading.RLock()
        self._backfill_queue: set[str] = set()
        self._backfill_attempted: dict[str, int] = {}
        self._last_prune = 0
        self._last_message: str | None = None
        self._cycle_count = 0
        self._manual_message_until = 0
        self._manual_message: dict[str, Any] | None = None
        self._status: dict[str, Any] = {
            "version": VERSION,
            "online": False,
            "state": "offline",
            "message": "Starting CryptoGotchi…" if cfg.get("main", {}).get("language", "en") == "en" else "Démarrage de CryptoGotchi…",
            "last_update": None,
            "error": None,
            "coins": [],
            "breadth": {"up": 0, "down": 0, "flat": 0, "average": None},
            "last_alert": None,
            "notification_results": [],
            "notifications_paused": bool(cfg.get("notifications", {}).get("paused", False)),
            "system": collect_system_info(),
            "network": {"economy": economy_state(cfg), "usage_today_bytes": 0, "requests_today": 0},
            "companion": self.brain.snapshot(cfg.get("main", {}).get("language", "en"), cfg.get("personality", {})),
            "journals": self.brain.journals(5),
            "display": self.display.info(),
            "cycle_count": 0,
            "asset_limit": self.active_asset_limit(cfg),
            "ignored_active_assets": 0,
            "companion_selection": [],
            "ranking": self.ranking.status({}),
        }

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        try:
            self.display.update(self.status())
            self._set_status(display=self.display.info())
        except Exception as exc:
            log.warning("Initialisation anticipée de l'écran impossible: %s", exc)
        self.thread = threading.Thread(target=self._run, name="cryptogotchi-market", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout=8)
        self.display.close()

    def status(self) -> dict[str, Any]:
        with self._status_lock:
            return json.loads(json.dumps(self._status))

    def force_refresh(self) -> None:
        self.wake_event.set()

    def request_backfill(self, coin_id: str) -> None:
        with self._backfill_lock:
            self._backfill_queue.add(str(coin_id))
        self.force_refresh()

    def set_notifications_paused(self, paused: bool) -> bool:
        def update(cfg):
            cfg.setdefault("notifications", {})["paused"] = bool(paused)
        self.config_manager.update(update)
        self._set_status(notifications_paused=bool(paused))
        current = self.status()
        language = self.config_manager.load().get("main", {}).get("language", "en")
        current["message"] = (("External alerts paused." if paused else "External alerts resumed.") if language == "en" else ("Alertes externes en pause." if paused else "Alertes externes réactivées."))
        self.display.update(current)
        return bool(paused)

    def toggle_notifications(self) -> bool:
        cfg = self.config_manager.load()
        paused = not bool(cfg.get("notifications", {}).get("paused", False))
        return self.set_notifications_paused(paused)

    @staticmethod
    def active_asset_limit(cfg: dict[str, Any]) -> int:
        try:
            requested = int(cfg.get("main", {}).get("max_active_assets", 50) or 50)
        except (TypeError, ValueError):
            requested = 50
        return max(1, min(HARD_MAX_ACTIVE_ASSETS, requested))

    def companion_selected_ids(self) -> list[str]:
        cfg = self.config_manager.load()
        maximum = max(1, min(5, int(cfg.get("companion", {}).get("max_analysis_assets", 5) or 5)))
        active = [coin for coin in cfg.get("coins", []) if coin.get("enabled", True)][:self.active_asset_limit(cfg)]
        known = {str(coin.get("id")) for coin in active}
        stored = self.db.get_state("companion:selected_coin_ids", [])
        selected = [str(item) for item in stored] if isinstance(stored, list) else []
        selected = [item for item in selected if item in known][:maximum]
        if selected:
            return selected
        favorites = [str(coin.get("id")) for coin in active if coin.get("favorite")]
        if favorites:
            return favorites[:maximum]
        status_ids = [str(coin.get("id")) for coin in self.status().get("coins", []) if coin.get("id")]
        return status_ids[:1]

    def set_companion_selection(self, coin_ids: list[str]) -> list[str]:
        cfg = self.config_manager.load()
        maximum = max(1, min(5, int(cfg.get("companion", {}).get("max_analysis_assets", 5) or 5)))
        active = [coin for coin in cfg.get("coins", []) if coin.get("enabled", True)][:self.active_asset_limit(cfg)]
        enabled = {str(coin.get("id")) for coin in active}
        clean: list[str] = []
        for coin_id in coin_ids:
            value = str(coin_id or "").strip().lower()
            if value in enabled and value not in clean:
                clean.append(value)
            if len(clean) >= maximum:
                break
        if not clean:
            raise ValueError("Select at least one active asset." if cfg.get("main", {}).get("language") == "en" else "Sélectionne au moins un actif surveillé.")
        self.db.set_state("companion:selected_coin_ids", clean)
        return clean

    def selected_coins_status(self, coin_ids: list[str] | None = None) -> list[dict[str, Any]]:
        wanted = coin_ids or self.companion_selected_ids()
        by_id = {str(coin.get("id")): coin for coin in (self.status().get("coins", []) or [])}
        return [by_id[item] for item in wanted if item in by_id]

    def selected_coin_status(self) -> dict[str, Any] | None:
        selected = self.selected_coins_status()
        return selected[0] if selected else None

    def _technical_analysis_for_coin(self, coin_status: dict[str, Any], cfg: dict[str, Any], language: str, now: int | None = None) -> dict[str, Any]:
        now = int(now or time.time())
        fiat = str(coin_status.get("fiat") or cfg.get("main", {}).get("fiat", "eur")).lower()
        source = str(coin_status.get("source") or "coingecko").lower()
        history_hours = max(24, min(72, int(cfg.get("main", {}).get("history_hours", 72) or 72)))
        samples = self.db.samples_since(
            str(coin_status.get("id") or ""),
            now - history_hours * 3600,
            quote_currency=fiat,
            source=source,
        )
        session = describe_market_session(coin_status, cfg.get("main", {}).get("timezone", "UTC"), language)
        analysis = analyze_market(coin_status, samples, now, language, session=session)
        analysis["id"] = str(coin_status.get("id") or "")
        analysis["asset_kind"] = str(coin_status.get("asset_kind") or "crypto")
        analysis["source"] = source
        return analysis

    def selected_coin_analyses(self, coin_ids: list[str] | None = None) -> list[dict[str, Any]]:
        cfg = self.config_manager.load()
        language = cfg.get("main", {}).get("language", "en")
        now = int(time.time())
        analyses: list[dict[str, Any]] = []
        for coin in self.selected_coins_status(coin_ids):
            analyses.append(self._technical_analysis_for_coin(coin, cfg, language, now))
        return analyses

    def display_coin_analysis(self) -> dict[str, Any] | None:
        cfg = self.config_manager.load()
        language = cfg.get("main", {}).get("language", "en")
        now = int(time.time())
        coin = self.display_coin_status()
        if not coin:
            return None
        return self._technical_analysis_for_coin(coin, cfg, language, now)

    def display_coin_status(self) -> dict[str, Any] | None:
        status = self.status()
        coins = status.get("coins", []) or []
        if not coins:
            return None
        index = int((status.get("display") or {}).get("coin_index", 0) or 0)
        return coins[index % len(coins)]

    @staticmethod
    def _ai_summary(state: str, evaluated_or_coins: list[dict[str, Any]], breadth: dict[str, Any] | None = None) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for item in evaluated_or_coins[:12]:
            if "market" in item:
                market = item.get("market", {})
                coin = item.get("coin", {})
                metrics = item.get("metrics", {})
            else:
                market = item
                coin = item
                metrics = item.get("metrics", {})
            rows.append({
                "id": str(coin.get("id") or market.get("id") or "")[:80],
                "symbol": str(coin.get("symbol") or market.get("symbol") or "?")[:12],
                "price": market.get("price"),
                "change_5m": metrics.get("5m"),
                "change_15m": metrics.get("15m"),
                "change_1h": metrics.get("1h"),
                "change_24h": market.get("change_24h"),
                "volume_ratio": metrics.get("volume_ratio"),
            })
        return {"state": state, "coins": rows, "breadth": breadth or {}}

    def _hold_manual_message(self, message: str, companion: dict[str, Any]) -> None:
        cfg = self.config_manager.load()
        seconds = max(15, min(900, int(cfg.get("companion", {}).get("manual_message_hold_seconds", 120) or 120)))
        self._manual_message_until = int(time.time()) + seconds
        self._manual_message = {"message": message, "companion": dict(companion)}

    def interact(self, action: str) -> dict[str, Any]:
        cfg = self.config_manager.load()
        language = cfg.get("main", {}).get("language", "en")
        result = self.brain.interaction(action, language)
        companion = {**self.brain.snapshot(language, cfg.get("personality", {})), **result}
        companion["engine"] = "micro-brain-v2"
        companion["is_llm"] = False
        self._hold_manual_message(result["message"], companion)
        self._set_status(message=result["message"], companion=companion, journals=self.brain.journals(5))
        self.display.set_page("companion")
        self.display.update(self.status())
        self._set_status(display=self.display.info())
        return result

    def ask_selected_coins(self, coin_ids: list[str] | None = None, *, persist_selection: bool = True) -> str:
        cfg = self.config_manager.load()
        language = cfg.get("main", {}).get("language", "en")
        if coin_ids is not None and persist_selection:
            selected_ids = self.set_companion_selection(coin_ids)
        elif coin_ids is not None:
            active = [coin for coin in cfg.get("coins", []) if coin.get("enabled", True)][:self.active_asset_limit(cfg)]
            allowed = {str(coin.get("id")) for coin in active}
            maximum = max(1, min(5, int(cfg.get("companion", {}).get("max_analysis_assets", 5) or 5)))
            selected_ids = []
            for raw in coin_ids:
                value = str(raw or "").strip().lower()
                if value in allowed and value not in selected_ids:
                    selected_ids.append(value)
                if len(selected_ids) >= maximum:
                    break
            if not selected_ids:
                raise ValueError("No active asset is available." if language == "en" else "Aucun actif actif n’est disponible.")
        else:
            selected_ids = self.companion_selected_ids()
        coins = self.selected_coins_status(selected_ids)
        analyses = self.selected_coin_analyses(selected_ids)
        fallback_local = compare_analyses(analyses, language) if analyses else self.brain.ask_about_coins(coins, language, cfg.get("personality", {}).get("profile", "sage"))
        economy = economy_state(cfg)
        result = None
        if cfg.get("ai", {}).get("mode") == "external" and economy.get("allow_external_ai", True):
            state = str(self.status().get("state", "calm"))
            ai_payload = self._ai_summary(state, coins, self.status().get("breadth", {}))
            ai_payload["technical_analysis"] = [
                {
                    "symbol": item.get("symbol"),
                    "verdict": item.get("verdict"),
                    "verdict_phrase": item.get("verdict_phrase"),
                    "timeframes": {
                        name: {
                            "trend": frame.get("trend"),
                            "regime": frame.get("regime"),
                            "support": frame.get("support_text"),
                            "resistance": frame.get("resistance_text"),
                            "bias": frame.get("bias"),
                            "change": frame.get("change"),
                        }
                        for name, frame in (item.get("timeframes") or {}).items()
                    },
                    "session": (item.get("session") or {}).get("summary", ""),
                }
                for item in analyses
            ]
            result = self.narrative_ai.generate(
                cfg,
                ai_payload,
                fallback_local,
                language,
                purpose="compare selected assets on 15m, 1h and 4h" if len(coins) > 1 else "explain the selected asset on 15m, 1h and 4h",
            )
        if result and result.ok:
            message = result.text
        elif result and not cfg.get("ai", {}).get("fallback_local", True):
            message = "External AI is unavailable." if language == "en" else "L’IA externe est indisponible."
        else:
            message = fallback_local
        companion = self.brain.snapshot(language, cfg.get("personality", {}))
        companion.update({
            "message": message,
            "thought": ("Comparing the 15m, 1h and 4h views without pretending certainty." if language == "en" else
                        "Je compare les vues 15 min, 1 h et 4 h sans prétendre à la certitude."),
            "engine": f"external-{result.provider}" if result and result.ok else "technical-sentinel-v2",
            "is_llm": bool(result and result.ok and result.provider != "local"),
            "ai_error": result.error if result and not result.ok else "",
            "selected_assets": [str(coin.get("symbol") or coin.get("id")) for coin in coins],
            "technical_analysis": analyses,
        })
        self._hold_manual_message(message, companion)
        self._set_status(
            message=message,
            companion=companion,
            journals=self.brain.journals(5),
            companion_selection=selected_ids if persist_selection else self.companion_selected_ids(),
        )
        self.display.set_page("companion")
        self.display.update(self.status())
        self._set_status(display=self.display.info())
        return message

    def ask_selected_coin(self) -> str:
        """LCD action: analyze the asset currently displayed on the physical screen."""
        coin = self.display_coin_status()
        if coin and coin.get("id"):
            return self.ask_selected_coins([str(coin["id"])], persist_selection=False)
        return self.ask_selected_coins()

    def create_journal_now(self) -> dict[str, Any] | None:
        cfg = self.config_manager.load()
        entry = self.brain.force_journal(
            cfg.get("main", {}).get("language", "en"),
            cfg.get("main", {}).get("name", "CryptoGotchi"),
        )
        if entry:
            self._set_status(message=entry["text"], journals=self.brain.journals(5))
            self.display.set_page("journal")
            self.display.update(self.status())
            self._set_status(display=self.display.info())
        return entry

    def _maybe_daily_journal(self, cfg: dict[str, Any], now: int) -> dict[str, Any] | None:
        section = cfg.get("companion", {})
        if not section.get("daily_journal", True):
            return None
        try:
            zone = ZoneInfo(str(cfg.get("main", {}).get("timezone", "UTC")))
        except Exception:
            zone = ZoneInfo("UTC")
        local = datetime.fromtimestamp(now, zone)
        if local.hour < max(0, min(23, int(section.get("journal_hour", 22)))):
            return None
        marker = f"auto_journal:{local.date().isoformat()}:{cfg.get('main', {}).get('language', 'en')}"
        if self.db.get_state(marker, False):
            return None
        entry = self.brain.force_journal(
            cfg.get("main", {}).get("language", "en"),
            cfg.get("main", {}).get("name", "CryptoGotchi"),
            now,
        )
        if entry:
            self.db.set_state(marker, True)
        return entry

    def _set_status(self, **kwargs) -> None:
        with self._status_lock:
            self._status.update(kwargs)

    @staticmethod
    def _downsample(values: list[float], maximum: int = 72) -> list[float]:
        if len(values) <= maximum:
            return values
        step = (len(values) - 1) / (maximum - 1)
        return [values[round(index * step)] for index in range(maximum)]

    @staticmethod
    def _sanitize_history(
        history: list[dict[str, Any]],
        market: dict[str, Any],
        max_jump_percent: float = 8.0,
    ) -> tuple[list[dict[str, Any]], str]:
        """Return a trustworthy contiguous suffix for chart rendering.

        A legacy currency/source jump usually appears as one large vertical
        step at the end of an otherwise calm series. If that step contradicts
        the provider-reported 1h/24h move, the old prefix is excluded rather
        than drawn or used to narrate the market.
        """
        clean: list[dict[str, Any]] = []
        for row in history:
            try:
                price = float(row["price"])
                ts = int(row["ts"])
            except (KeyError, TypeError, ValueError):
                continue
            if price > 0:
                clean.append({**row, "price": price, "ts": ts})
        clean.sort(key=lambda item: item["ts"])
        if len(clean) < 2:
            return clean, ""
        provider_1h = market.get("change_1h")
        provider_24h = market.get("change_24h")
        expected = max(abs(float(provider_1h or 0)), abs(float(provider_24h or 0)))
        threshold = max(float(max_jump_percent), expected * 2.5 + 2.0)
        reset_index = None
        for index in range(1, len(clean)):
            previous = clean[index - 1]["price"]
            current = clean[index]["price"]
            jump = abs((current - previous) / previous * 100.0) if previous else 0.0
            if jump > threshold:
                reset_index = index
        if reset_index is not None:
            suffix = clean[reset_index:]
            if suffix:
                return suffix, "Legacy discontinuity filtered"
        return clean, ""

    @staticmethod
    def _breadth(changes: list[float]) -> dict[str, Any]:
        if not changes:
            return {"up": 0, "down": 0, "flat": 0, "average": None}
        return {
            "up": sum(1 for value in changes if value > 0.05),
            "down": sum(1 for value in changes if value < -0.05),
            "flat": sum(1 for value in changes if -0.05 <= value <= 0.05),
            "average": sum(changes) / len(changes),
        }

    def _consume_usage(self, now: int) -> dict[str, Any]:
        transfer = {"bytes": 0, "requests": 0}
        for provider in (self.provider, self.gold_provider):
            consume = getattr(provider, "consume_transfer_stats", None)
            stats = consume() if callable(consume) else {"bytes": 0, "requests": 0}
            transfer["bytes"] += int(stats.get("bytes", 0) or 0)
            transfer["requests"] += int(stats.get("requests", 0) or 0)
        if transfer["bytes"] or transfer["requests"]:
            usage = self.db.add_network_usage(transfer["bytes"], transfer["requests"], now)
        else:
            usage = self.db.network_usage_today(now)
        elapsed = max(300, now - int(usage.get("first_ts", now)))
        estimated = int(usage["bytes"] / elapsed * 86400) if usage["bytes"] else 0
        return {
            "usage_today_bytes": usage["bytes"],
            "requests_today": usage["requests"],
            "estimated_daily_bytes": estimated,
        }

    def _perform_backfills(
        self,
        cfg: dict[str, Any],
        enabled_coins: list[dict[str, Any]],
        fiat: str,
        now: int,
        allow: bool,
    ) -> set[str]:
        if not allow or not callable(getattr(self.provider, "fetch_history", None)):
            return set()
        with self._backfill_lock:
            queued = list(self._backfill_queue)
        candidates: list[str] = []
        coingecko_coins = [coin for coin in enabled_coins if str(coin.get("source", "coingecko")) == "coingecko"]
        known = {coin["id"] for coin in coingecko_coins}
        for coin_id in queued:
            if coin_id in known and coin_id not in candidates:
                candidates.append(coin_id)
        for coin in coingecko_coins:
            coin_id = coin["id"]
            if self.db.sample_count(coin_id, now - 24 * 3600, fiat, "coingecko") < 8 and coin_id not in candidates:
                candidates.append(coin_id)
        budget = max(1, min(4, int(cfg.get("connectivity", {}).get("history_backfill_per_cycle", 2))))
        completed: set[str] = set()
        for coin_id in candidates[:budget]:
            last_attempt = self._backfill_attempted.get(coin_id, 0)
            cooldown = 300 if coin_id in queued else 3600
            if last_attempt and now - last_attempt < cooldown:
                continue
            self._backfill_attempted[coin_id] = now
            try:
                history = self.provider.fetch_history(coin_id, fiat, days=1)
                inserted = self.db.add_samples(coin_id, history, fiat, "coingecko")
                if inserted:
                    completed.add(coin_id)
                    log.info("Historique initialisé pour %s: %s points", coin_id, inserted)
                with self._backfill_lock:
                    self._backfill_queue.discard(coin_id)
            except Exception as exc:
                log.warning("Historique initial impossible pour %s: %s", coin_id, exc)
        return completed

    def _maybe_social_digest(
        self,
        cfg: dict[str, Any],
        state: str,
        evaluated: list[dict[str, Any]],
        now: int,
        allow_public: bool,
    ) -> list[dict[str, Any]]:
        digest_cfg = cfg.get("social_digest", {})
        public_channels = cfg.get("notifications", {})
        has_public_channel = bool(public_channels.get("mastodon", {}).get("enabled") or public_channels.get("bluesky", {}).get("enabled"))
        if (
            not digest_cfg.get("enabled", False)
            or not allow_public
            or not cfg.get("security", {}).get("allow_public_posts", False)
            or not has_public_channel
        ):
            return []
        interval = max(1, int(digest_cfg.get("interval_hours", 4))) * 3600
        last_ts = int(self.db.get_state("social_digest:last_ts", 0) or 0)
        if now - last_ts < interval:
            return []
        if digest_cfg.get("only_when_changed", True):
            changes = [
                abs(float(item.get("metrics", {}).get("15m") or item.get("metrics", {}).get("24h") or 0))
                for item in evaluated
            ]
            minimum = abs(float(digest_cfg.get("minimum_move_percent", 0.5)))
            if not changes or max(changes) < minimum:
                return []
        alert = {
            "alert_key": f"market:digest:{now // interval}",
            "coin_id": None,
            "symbol": "MARKET",
            "rule": "social_digest",
            "severity": "info",
            "message": self.brain.social_digest(
                state, evaluated, cfg.get("main", {}).get("name", "CryptoGotchi"), cfg.get("main", {}).get("language", "en")
            ),
            "ts": now,
            "metrics": {},
            "social_post": True,
            "private_notify": False,
        }
        results = self.notifiers.dispatch(alert)
        if any(result.get("ok") and result.get("channel") in {"mastodon", "bluesky"} for result in results):
            self.db.set_state("social_digest:last_ts", now)
            self.db.record_alert(alert, "{}")
        return results

    def run_once(self) -> None:
        cfg = self.config_manager.load()
        self.provider.update_config(cfg)
        self.gold_provider.update_config(cfg)
        connection = active_connection_info()
        economy = economy_state(cfg, connection)
        all_enabled_coins = [coin for coin in cfg.get("coins", []) if coin.get("enabled", True)]
        active_limit = self.active_asset_limit(cfg)
        enabled_coins = all_enabled_coins[:active_limit]
        ignored_active_assets = max(0, len(all_enabled_coins) - len(enabled_coins))
        coin_by_id = {coin["id"]: coin for coin in enabled_coins}
        fiat = str(cfg["main"].get("fiat", "eur")).lower()
        language = "fr" if cfg.get("main", {}).get("language") == "fr" else "en"
        now = int(time.time())
        coingecko_coins = [coin for coin in enabled_coins if str(coin.get("source", "coingecko")) == "coingecko"]
        gold_coins = [coin for coin in enabled_coins if str(coin.get("source", "coingecko")) == "gold_api"]
        markets = self.provider.fetch_markets([coin["id"] for coin in coingecko_coins], fiat)
        if gold_coins:
            markets.extend(self.gold_provider.fetch_markets(gold_coins, fiat))
        market_by_id = {market["id"]: market for market in markets}
        before_counts = {
            coin["id"]: self.db.sample_count(
                coin["id"], now - 24 * 3600,
                str(coin.get("quote_currency") or fiat).lower(),
                str(coin.get("source") or "coingecko").lower(),
            ) for coin in enabled_coins
        }
        freshly_backfilled = self._perform_backfills(cfg, enabled_coins, fiat, now, economy["allow_history_backfill"])
        evaluated: list[dict[str, Any]] = []
        all_alerts: list[dict[str, Any]] = []
        changes: list[float] = []
        volume_ratios: list[float] = []

        for coin in enabled_coins:
            market = market_by_id.get(coin["id"])
            if not market:
                continue
            market.update({
                "asset_kind": coin.get("asset_kind", "crypto"),
                "trading_mode": coin.get("trading_mode", "24x7"),
                "data_note": asset_data_note(coin, language),
                "data_note_key": coin.get("data_note_key", ""),
                "include_in_market_mood": bool(coin.get("include_in_market_mood", True)),
            })
            quote = str(market.get("fiat") or fiat).lower()
            source = str(market.get("source") or coin.get("source") or "coingecko").lower()
            self.db.add_sample(
                market["id"], now, market["price"], market.get("volume"), market.get("change_24h"),
                quote, source,
            )
            metrics, alerts = self.alert_engine.evaluate_coin(market, coin, now, language)
            # Une crypto fraîchement ajoutée reçoit son historique immédiatement,
            # mais on évite de publier une alerte rétroactive au premier cycle.
            if coin["id"] in freshly_backfilled and before_counts.get(coin["id"], 0) < 2:
                alerts = []
            evaluated.append({"market": market, "coin": coin, "metrics": metrics})
            all_alerts.extend(alerts)
            if coin.get("include_in_market_mood", True) and not market.get("is_stale") and market.get("market_status") != "closed":
                change = metrics.get("15m")
                if change is None:
                    change = metrics.get("24h")
                if change is not None:
                    changes.append(float(change))
                if metrics.get("volume_ratio") is not None:
                    volume_ratios.append(float(metrics["volume_ratio"]))

        all_alerts.extend(self.alert_engine.evaluate_market_breadth(evaluated, cfg.get("market_rules", {}), now, language))

        notification_results: list[dict[str, Any]] = []
        for alert in all_alerts:
            if not economy["allow_public_posts"]:
                alert = dict(alert)
                alert["social_post"] = False
            self.db.record_alert(alert, json.dumps(alert.get("metrics", {}), ensure_ascii=False))
            notification_results.extend(self.notifiers.dispatch(alert))

        state = choose_state(changes, volume_ratios, online=True)
        personality_cfg = cfg.get("personality", {})
        companion = self.brain.observe(
            state,
            evaluated,
            language,
            self._last_message,
            personality_cfg.get("profile", "sage"),
            now,
            len(all_alerts),
            personality=personality_cfg,
            coin_count=len(enabled_coins),
            network_type=str(connection.get("type", "unknown")),
            name=cfg.get("main", {}).get("name", "CryptoGotchi"),
        )
        daily_entry = self._maybe_daily_journal(cfg, now)
        if daily_entry:
            companion["journal_created"] = daily_entry
        local_message = all_alerts[-1]["message"] if all_alerts else companion["message"]
        ai_cfg = cfg.get("ai", {})
        use_external = (
            ai_cfg.get("mode") == "external"
            and economy.get("allow_external_ai", True)
            and (not ai_cfg.get("only_for_alerts", False) or bool(all_alerts))
        )
        if use_external:
            ai_result = self.narrative_ai.generate(
                cfg,
                self._ai_summary(state, evaluated, self._breadth(changes)),
                local_message,
                language,
                purpose="threshold alert" if all_alerts else "market observation",
            )
            companion["ai_error"] = ai_result.error
            if ai_result.ok:
                companion["message"] = ai_result.text
                companion["engine"] = f"external-{ai_result.provider}"
                companion["model"] = ai_result.model
                companion["is_llm"] = ai_result.provider != "local"
                message = ai_result.text
            else:
                if ai_cfg.get("fallback_local", True):
                    companion["engine"] = "micro-brain-v2-fallback"
                    message = local_message
                else:
                    companion["engine"] = f"external-{ai_result.provider}-error"
                    message = "External narrative AI is unavailable." if language == "en" else "L’IA narrative externe est indisponible."
        else:
            companion["ai_error"] = ""
            message = local_message
        if not personality_cfg.get("show_thoughts", True):
            companion["thought"] = ""
        if self._manual_message and now < self._manual_message_until:
            message = str(self._manual_message.get("message") or message)
            held = dict(self._manual_message.get("companion") or {})
            companion.update(held)
            companion["manual_hold_until"] = self._manual_message_until
        elif self._manual_message:
            self._manual_message = None
            self._manual_message_until = 0
        self._last_message = message

        coin_status: list[dict[str, Any]] = []
        chart_hours = max(1, min(48, int(cfg.get("provider", {}).get("chart_hours", 24))))
        for item in evaluated:
            row = dict(item["market"])
            row["metrics"] = item["metrics"]
            history = self.db.samples_since(
                row["id"], now - chart_hours * 3600,
                quote_currency=str(row.get("fiat") or fiat).lower(),
                source=str(row.get("source") or "coingecko").lower(),
            )
            clean_history, integrity_note = self._sanitize_history(
                history,
                row,
                float(cfg.get("provider", {}).get("max_stream_jump_percent", 8.0)),
            )
            values = [float(sample["price"]) for sample in clean_history]
            downsampled = self._downsample(values)
            row["sparkline"] = downsampled
            row["sparkline_meta"] = {
                "period_hours": chart_hours,
                "samples": len(clean_history),
                "raw_samples": len(history),
                "ready": len(clean_history) >= 2,
                "backfilled": row["id"] in freshly_backfilled,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "start": values[0] if values else None,
                "end": values[-1] if values else None,
                "source": row.get("source", "coingecko"),
                "quote": row.get("fiat", fiat),
                "integrity_note": integrity_note,
            }
            row["data_quality_warning"] = item["metrics"].get("quality_warning") or integrity_note
            coin_status.append(row)

        notification_results.extend(
            self._maybe_social_digest(cfg, state, evaluated, now, economy["allow_public_posts"])
        )
        usage = self._consume_usage(now)
        previous_status = self.status()
        last_alert = all_alerts[-1] if all_alerts else previous_status.get("last_alert")
        if last_alert is None:
            latest = self.db.latest_alerts(1)
            last_alert = latest[0] if latest else None
        self._cycle_count += 1
        status = {
            "version": VERSION,
            "online": True,
            "state": state,
            "message": message,
            "last_update": now,
            "error": None,
            "coins": coin_status,
            "breadth": self._breadth(changes),
            "last_alert": last_alert,
            "notification_results": notification_results[-20:],
            "notifications_paused": bool(cfg.get("notifications", {}).get("paused", False)),
            "system": collect_system_info(),
            "network": {"economy": economy, **usage},
            "companion": companion,
            "journals": self.brain.journals(5),
            "cycle_count": self._cycle_count,
            "asset_limit": active_limit,
            "ignored_active_assets": ignored_active_assets,
            "companion_selection": self.companion_selected_ids(),
        }
        ranking_result = None
        if self.ranking.should_sync(now):
            ranking_result = self.ranking.sync(status)
        status["ranking"] = {**self.ranking.status(status), "last_result": ranking_result}
        self._set_status(**status)
        self.display.update(self.status())
        self._set_status(display=self.display.info())
        if now - self._last_prune >= 3600:
            self.db.prune(int(cfg["main"].get("history_hours", 48)))
            self._last_prune = now

    def _run(self) -> None:
        while not self.stop_event.is_set():
            cfg = self.config_manager.load()
            refresh = economy_state(cfg)["refresh_seconds"]
            try:
                self.run_once()
            except Exception as exc:
                log.exception("Échec de l'actualisation du marché")
                now = int(time.time())
                usage = self._consume_usage(now)
                message = state_message("offline", cfg["main"].get("language", "en"), self._last_message)
                self._last_message = message
                economy = economy_state(cfg)
                personality_cfg = cfg.get("personality", {})
                companion = self.brain.observe(
                    "offline", [], cfg["main"].get("language", "en"), message,
                    personality_cfg.get("profile", "sage"), now, 0,
                    personality=personality_cfg,
                    coin_count=len([coin for coin in cfg.get("coins", []) if coin.get("enabled", True)]),
                    network_type=str((economy.get("connection") or {}).get("type", "none")),
                    name=cfg.get("main", {}).get("name", "CryptoGotchi"),
                )
                self._set_status(
                    online=False,
                    state="offline",
                    message=message,
                    error=str(exc)[:300],
                    last_update=now,
                    notifications_paused=bool(cfg.get("notifications", {}).get("paused", False)),
                    system=collect_system_info(),
                    network={"economy": economy, **usage},
                    companion=companion,
                    journals=self.brain.journals(5),
                )
                self.display.update(self.status())
                self._set_status(display=self.display.info())
            self.wake_event.wait(refresh)
            self.wake_event.clear()
