from __future__ import annotations

import copy
import os
import secrets
import threading
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from .toml_writer import dumps as toml_dumps


COIN_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "alerts_enabled": True,
    "source": "coingecko",
    "asset_kind": "crypto",
    "trading_mode": "24x7",
    "data_note": "",
    "data_note_key": "",
    "include_in_market_mood": True,
    "drop_5m": 2.0,
    "rise_5m": 2.0,
    "drop_15m": 3.0,
    "rise_15m": 3.0,
    "drop_1h": 5.0,
    "rise_1h": 5.0,
    "drop_24h": 10.0,
    "rise_24h": 10.0,
    "volume_multiplier": 2.5,
    "new_high_24h": False,
    "new_low_24h": False,
    "cooldown_minutes": 30,
    "social_post": False,
    "favorite": False,
}


def _coin(coin_id: str, symbol: str, name: str, **overrides: Any) -> dict[str, Any]:
    return {"id": coin_id, "symbol": symbol, "name": name, **copy.deepcopy(COIN_DEFAULTS), **overrides}


DEFAULT_CONFIG: dict[str, Any] = {
    "main": {
        "name": "CryptoGotchi",
        "language": "en",
        "fiat": "eur",
        "refresh_seconds": 60,
        "history_hours": 72,
        "timezone": "Europe/Brussels",
        "web_host": "0.0.0.0",
        "web_port": 8080,
        "cooldown_minutes": 30,
        "device_profile": "pi_zero_2w",
        "config_revision": 12,
        "max_active_assets": 50,
        "logo_path": "logo.png",
    },
    "security": {
        "username": "admin",
        "password_hash": "",
        "secret_key": "",
        "allow_public_posts": False,
        "max_public_posts_per_hour": 3,
    },
    "provider": {
        "name": "coingecko",
        "base_url": "https://api.coingecko.com/api/v3",
        "api_key": "",
        "timeout_seconds": 15,
        "chart_hours": 24,
        "gold_api_base_url": "https://api.gold-api.com",
        "freshness_seconds": 600,
        "fx_api_base_url": "https://api.frankfurter.dev/v2",
        "max_stream_jump_percent": 8.0,
    },
    "connectivity": {
        "bluetooth_enabled": True,
        "data_saver_mode": "auto",
        "auto_on_bluetooth": True,
        "auto_on_metered": True,
        "economy_refresh_seconds": 300,
        "history_backfill_in_economy": False,
        "history_backfill_per_cycle": 2,
        "public_posts_in_economy": False,
        "external_ai_in_economy": False,
    },
    "personality": {
        "profile": "sage",
        "show_thoughts": True,
        "humor": 25,
        "energy": 55,
        "prudence": 80,
        "technical_level": 55,
        "talk_frequency": 55,
        "optimism": 50,
        "verbosity": 45,
        "custom_identity": "A loyal market companion that stays factual, curious and calm.",
        "animations": True,
        "accessory": "auto",
    },
    "ai": {
        "mode": "local",
        "provider": "ollama",
        "endpoint": "http://192.168.1.10:11434",
        "model": "gemma3:4b",
        "api_key": "",
        "timeout_seconds": 20,
        "max_characters": 240,
        "only_for_alerts": False,
        "fallback_local": True,
        "custom_system_prompt": "",
    },
    "companion": {
        "daily_journal": True,
        "journal_hour": 22,
        "achievement_popups": True,
        "interaction_cooldown_seconds": 2,
        "manual_message_hold_seconds": 120,
        "max_analysis_assets": 5,
    },
    "social_digest": {
        "enabled": False,
        "interval_hours": 4,
        "only_when_changed": True,
        "minimum_move_percent": 0.5,
    },
    "display": {
        "type": "waveshare_lcd_1in44",
        "waveshare_model": "epd2in13_V4",
        "rotation": 0,
        "partial_refresh": False,
        "brightness": 90,
        "dim_brightness": 18,
        "backlight_timeout_seconds": 0,
        "screen_sleep_seconds": 0,
        "page_cycle_seconds": 12,
        "alert_hold_seconds": 20,
        "auto_cycle": True,
        "spi_speed_hz": 9000000,
        "animation_fps": 2,
        "show_accessories": True,
    },
    "market_rules": {
        "enabled": True,
        "breadth_window_minutes": 15,
        "breadth_drop_percent": 3.0,
        "breadth_count": 3,
        "breadth_rise_percent": 3.0,
        "breadth_rise_count": 3,
        "cooldown_minutes": 45,
    },
    "notifications": {
        "paused": False,
        "dashboard": {"enabled": True, "sound_volume": 65, "minimum_severity": "info", "browser_notifications": True},
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "discord": {"enabled": False, "webhook_url": ""},
        "mastodon": {"enabled": False, "instance_url": "", "access_token": "", "visibility": "unlisted"},
        "bluesky": {"enabled": False, "service_url": "https://bsky.social", "handle": "", "app_password": ""},
        "webhook": {"enabled": False, "url": "", "bearer_token": ""},
    },
    "ranking": {
        "enabled": False,
        "endpoint_url": "",
        "public_name": "",
        "api_token": "",
        "sync_interval_hours": 6,
        "share_country": False,
        "country_code": "",
    },
    "coins": [
        _coin("bitcoin", "BTC", "Bitcoin", favorite=True),
        _coin("ethereum", "ETH", "Ethereum"),
    ],
}



def canonical_data_note_key(coin: dict[str, Any]) -> str:
    """Return a stable, asset-specific note key.

    Older releases stored free-form notes in the TOML file. A stale value could
    follow the next asset added from the browser and make SPCX display the XAU
    explanation. v0.6.2 derives the note from immutable asset metadata instead.
    """
    coin_id = str(coin.get("id") or "").lower()
    symbol = str(coin.get("symbol") or "").upper()
    name = str(coin.get("name") or "").lower()
    source = str(coin.get("source") or "coingecko").lower()
    kind = str(coin.get("asset_kind") or "crypto").lower()
    if source == "gold_api" or coin_id.startswith("spot-"):
        return "spot_metal"
    if kind == "tokenized_asset" or "robinhood token" in name or symbol == "SPCX":
        return "tokenized_asset"
    if kind == "crypto_token" or (source == "coingecko" and symbol in {"XAU", "XAG", "XPT", "XPD"}):
        return "crypto_metal_ticker"
    return ""


def asset_data_note(coin: dict[str, Any], language: str = "en") -> str:
    key = canonical_data_note_key(coin)
    symbol = str(coin.get("symbol") or "").upper()
    fr = language == "fr"
    if key == "spot_metal":
        return (
            "Cours spot par once troy. L’historique intrajournalier se construit localement."
            if fr else
            "Spot price per troy ounce. Intraday history is built locally."
        )
    if key == "tokenized_asset":
        return (
            "Actif tokenisé négocié 24 h/24 sur des marchés crypto ; ce n’est pas une action officielle cotée."
            if fr else
            "Tokenized asset traded 24/7 on crypto markets; it is not an official exchange-listed share."
        )
    if key == "crypto_metal_ticker":
        return (
            f"Jeton crypto utilisant le symbole {symbol} ; ce n’est pas le cours spot du métal."
            if fr else
            f"Crypto token using the {symbol} ticker; it is not the spot metal quote."
        )
    return ""

def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _normalize_coins(cfg: dict[str, Any]) -> None:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in cfg.get("coins", []):
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        had_alerts_enabled = "alerts_enabled" in raw
        coin = {**copy.deepcopy(COIN_DEFAULTS), **raw}
        coin["id"] = str(coin["id"]).strip().lower()
        coin["symbol"] = str(coin.get("symbol") or coin["id"][:6]).strip().upper()
        coin["name"] = str(coin.get("name") or coin["id"]).strip()
        coin["source"] = str(coin.get("source") or "coingecko").strip().lower()
        coin["asset_kind"] = str(coin.get("asset_kind") or "crypto").strip().lower()
        coin["trading_mode"] = str(coin.get("trading_mode") or "24x7").strip().lower()
        coin["data_note"] = str(coin.get("data_note") or "").strip()
        # Stable CoinGecko-ID migrations. Symbols such as BCH are not valid
        # CoinGecko IDs and previously caused repeated 404 history warnings.
        lowered_name = coin["name"].lower()
        if coin["id"] == "bch":
            coin.update({"id": "bitcoin-cash", "symbol": "BCH", "name": "Bitcoin Cash"})
            lowered_name = coin["name"].lower()
        # v0.5 market-integrity migrations for assets commonly confused in v0.4.
        if coin["id"] == "gold-8" and coin["symbol"] == "XAU":
            coin.update({
                "id": "spot-xau", "symbol": "XAU", "provider_symbol": "XAU",
                "name": "Gold Spot", "source": "gold_api", "asset_kind": "commodity",
                "trading_mode": "market_session",
                "data_note": "Spot gold per troy ounce from Gold API; intraday history is built locally.",
                "include_in_market_mood": False, "volume_multiplier": 0.0,
                "new_high_24h": False, "new_low_24h": False,
            })
        elif "robinhood token" in lowered_name or (coin["symbol"] == "SPCX" and "spacex" in lowered_name):
            coin.update({
                "asset_kind": "tokenized_asset", "trading_mode": "24x7",
                "data_note": "Tokenized asset traded on crypto markets 24/7; it is not an official exchange-listed SpaceX share.",
                "include_in_market_mood": False,
                "alerts_enabled": bool(coin.get("alerts_enabled", False)) if had_alerts_enabled else False,
            })
        elif coin["source"] == "coingecko" and coin["symbol"] in {"XAU", "XAG", "XPT", "XPD"}:
            coin.update({
                "asset_kind": "crypto_token", "trading_mode": "24x7",
                "data_note": f"Crypto token using the {coin['symbol']} ticker; it is not the spot metal quote.",
                "include_in_market_mood": False,
            })
        else:
            coin["include_in_market_mood"] = bool(coin.get("include_in_market_mood", coin["asset_kind"] == "crypto"))
        coin["data_note_key"] = canonical_data_note_key(coin)
        coin["data_note"] = asset_data_note(coin, "en")
        if coin["id"] in seen_ids:
            continue
        seen_ids.add(coin["id"])
        normalized.append(coin)
    cfg["coins"] = normalized


def default_config() -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["security"]["secret_key"] = secrets.token_hex(32)
    return cfg


def _import_boot_config(config_path: Path) -> None:
    marker = config_path.parent / ".boot_config_imported"
    if marker.exists():
        return
    candidates = [Path("/boot/firmware/cryptogotchi.toml"), Path("/boot/cryptogotchi.toml")]
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 10:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_bytes(candidate.read_bytes())
            config_path.chmod(0o600)
            marker.write_text("imported\n", encoding="utf-8")
            return


class ConfigManager:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _import_boot_config(self.path)
        if not self.path.exists():
            self.save(default_config())
        else:
            cfg = self.load()
            if not cfg.get("security", {}).get("secret_key"):
                cfg["security"]["secret_key"] = secrets.token_hex(32)
                self.save(cfg)

    def load(self) -> dict[str, Any]:
        with self._lock:
            with self.path.open("rb") as fh:
                raw = tomllib.load(fh)
            cfg = deep_merge(DEFAULT_CONFIG, raw)
            _normalize_coins(cfg)
            return cfg

    def save(self, cfg: dict[str, Any]) -> None:
        with self._lock:
            merged = deep_merge(DEFAULT_CONFIG, cfg)
            _normalize_coins(merged)
            if not merged["security"].get("secret_key"):
                merged["security"]["secret_key"] = secrets.token_hex(32)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_bytes(toml_dumps(merged).encode("utf-8"))
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)

    def update(self, updater) -> dict[str, Any]:
        with self._lock:
            cfg = self.load()
            updater(cfg)
            self.save(cfg)
            return cfg

    def public_snapshot(self) -> dict[str, Any]:
        cfg = self.load()
        cfg["security"]["password_hash"] = "***" if cfg["security"].get("password_hash") else ""
        cfg["security"]["secret_key"] = "***"
        for channel in cfg.get("notifications", {}).values():
            if not isinstance(channel, dict):
                continue
            for key in list(channel):
                if any(token in key for token in ("token", "password", "url")) and channel.get(key):
                    channel[key] = "***"
        if cfg.get("provider", {}).get("api_key"):
            cfg["provider"]["api_key"] = "***"
        if cfg.get("ai", {}).get("api_key"):
            cfg["ai"]["api_key"] = "***"
        return cfg
