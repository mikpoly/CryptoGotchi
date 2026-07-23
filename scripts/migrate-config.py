#!/usr/bin/env python3
"""Migrations sûres de configuration entre les versions CryptoGotchi."""
from __future__ import annotations

import sys
from pathlib import Path

# Permet d'exécuter ce script directement depuis le dépôt, avant même
# l'installation du paquet Python. L'installateur définit déjà PYTHONPATH,
# mais ce garde-fou rend aussi la migration fiable pour les contributeurs.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cryptogotchi.config import ConfigManager, asset_data_note, canonical_data_note_key


def main() -> int:
    config_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/etc/cryptogotchi/config.toml")
    manager = ConfigManager(config_path)
    cfg = manager.load()
    revision = int(cfg.get("main", {}).get("config_revision", 0) or 0)

    if revision < 3:
        display = cfg.setdefault("display", {})
        if int(display.get("backlight_timeout_seconds", 45) or 0) == 45:
            display["backlight_timeout_seconds"] = 0
        if int(display.get("screen_sleep_seconds", 300) or 0) == 300:
            display["screen_sleep_seconds"] = 0
        revision = 3
        print("Migration v0.2.3: écran permanent activé par défaut.")

    if revision < 4:
        cfg.setdefault("provider", {}).setdefault("chart_hours", 24)
        cfg.setdefault("connectivity", {}).update({
            "data_saver_mode": cfg.get("connectivity", {}).get("data_saver_mode", "auto"),
            "auto_on_bluetooth": cfg.get("connectivity", {}).get("auto_on_bluetooth", True),
            "auto_on_metered": cfg.get("connectivity", {}).get("auto_on_metered", True),
            "economy_refresh_seconds": cfg.get("connectivity", {}).get("economy_refresh_seconds", 300),
            "history_backfill_in_economy": cfg.get("connectivity", {}).get("history_backfill_in_economy", False),
            "history_backfill_per_cycle": cfg.get("connectivity", {}).get("history_backfill_per_cycle", 2),
            "public_posts_in_economy": cfg.get("connectivity", {}).get("public_posts_in_economy", False),
        })
        cfg.setdefault("personality", {}).setdefault("profile", "sage")
        cfg.setdefault("personality", {}).setdefault("show_thoughts", True)
        cfg.setdefault("social_digest", {}).update({
            "enabled": cfg.get("social_digest", {}).get("enabled", False),
            "interval_hours": cfg.get("social_digest", {}).get("interval_hours", 4),
            "only_when_changed": cfg.get("social_digest", {}).get("only_when_changed", True),
            "minimum_move_percent": cfg.get("social_digest", {}).get("minimum_move_percent", 0.5),
        })
        cfg.setdefault("main", {})["config_revision"] = 4
        print("Migration v0.3.0: graphiques 24 h, Micro-Brain et mode économie ajoutés.")

    if revision < 5:
        cfg.setdefault("connectivity", {}).setdefault("external_ai_in_economy", False)
        cfg.setdefault("personality", {}).update({
            "humor": cfg.get("personality", {}).get("humor", 25),
            "energy": cfg.get("personality", {}).get("energy", 55),
            "prudence": cfg.get("personality", {}).get("prudence", 80),
            "technical_level": cfg.get("personality", {}).get("technical_level", 55),
            "talk_frequency": cfg.get("personality", {}).get("talk_frequency", 55),
            "optimism": cfg.get("personality", {}).get("optimism", 50),
            "verbosity": cfg.get("personality", {}).get("verbosity", 45),
            "custom_identity": cfg.get("personality", {}).get("custom_identity", "A loyal market companion that stays factual, curious and calm."),
            "animations": cfg.get("personality", {}).get("animations", True),
            "accessory": cfg.get("personality", {}).get("accessory", "auto"),
        })
        cfg.setdefault("ai", {}).update({
            "mode": cfg.get("ai", {}).get("mode", "local"),
            "provider": cfg.get("ai", {}).get("provider", "ollama"),
            "endpoint": cfg.get("ai", {}).get("endpoint", "http://192.168.1.10:11434"),
            "model": cfg.get("ai", {}).get("model", "gemma3:4b"),
            "api_key": cfg.get("ai", {}).get("api_key", ""),
            "timeout_seconds": cfg.get("ai", {}).get("timeout_seconds", 20),
            "max_characters": cfg.get("ai", {}).get("max_characters", 240),
            "only_for_alerts": cfg.get("ai", {}).get("only_for_alerts", False),
            "fallback_local": cfg.get("ai", {}).get("fallback_local", True),
            "custom_system_prompt": cfg.get("ai", {}).get("custom_system_prompt", ""),
        })
        cfg.setdefault("companion", {}).update({
            "daily_journal": cfg.get("companion", {}).get("daily_journal", True),
            "journal_hour": cfg.get("companion", {}).get("journal_hour", 22),
            "achievement_popups": cfg.get("companion", {}).get("achievement_popups", True),
            "interaction_cooldown_seconds": cfg.get("companion", {}).get("interaction_cooldown_seconds", 2),
        })
        cfg.setdefault("display", {}).setdefault("animation_fps", 2)
        cfg.setdefault("display", {}).setdefault("show_accessories", True)
        for coin in cfg.get("coins", []):
            coin.setdefault("favorite", False)
        cfg.setdefault("main", {})["config_revision"] = 5
        revision = 5
        print("Migration v0.4.0: Companion Life, Micro-Brain v2, bilingual UI and optional AI added.")

    if revision < 6:
        cfg.setdefault("provider", {}).setdefault("gold_api_base_url", "https://api.gold-api.com")
        cfg.setdefault("provider", {}).setdefault("freshness_seconds", 600)
        # ConfigManager normalizes each existing asset here: quote/provider
        # isolation, known XAU correction and tokenized-asset labels.
        cfg.setdefault("main", {})["config_revision"] = 6
        print("Migration v0.5.0: market-integrity streams, real spot metals and asset labels added.")


    if revision < 7:
        provider = cfg.setdefault("provider", {})
        provider.setdefault("fx_api_base_url", "https://api.frankfurter.dev/v2")
        provider.setdefault("max_stream_jump_percent", 8.0)
        for coin in cfg.get("coins", []):
            if "alerts_enabled" not in coin:
                lowered = f"{coin.get('id','')} {coin.get('name','')} {coin.get('symbol','')}".lower()
                coin["alerts_enabled"] = not ("robinhood token" in lowered or "spcx" in lowered)
        cfg.setdefault("main", {})["config_revision"] = 7
        revision = 7
        print("Migration v0.6.0: clean market streams, provider 1h changes, fixed metals and robust Bluetooth added.")


    if revision < 8:
        for coin in cfg.get("coins", []):
            coin["data_note_key"] = canonical_data_note_key(coin)
            coin["data_note"] = asset_data_note(coin, "en")
        cfg.setdefault("main", {})["config_revision"] = 8
        revision = 8
        print("Migration v0.6.2: asset-specific data notes and Bluetooth pairing agent added.")

    if revision < 9:
        cfg.setdefault("main", {}).setdefault("max_active_assets", 50)
        cfg.setdefault("companion", {}).setdefault("manual_message_hold_seconds", 120)
        cfg.setdefault("companion", {}).setdefault("max_analysis_assets", 5)
        cfg.setdefault("notifications", {}).setdefault("dashboard", {
            "enabled": True,
            "sound_volume": 65,
            "minimum_severity": "info",
            "browser_notifications": True,
        })
        cfg.setdefault("ranking", {}).update({
            "enabled": cfg.get("ranking", {}).get("enabled", False),
            "endpoint_url": cfg.get("ranking", {}).get("endpoint_url", ""),
            "public_name": cfg.get("ranking", {}).get("public_name", ""),
            "api_token": cfg.get("ranking", {}).get("api_token", ""),
            "sync_interval_hours": cfg.get("ranking", {}).get("sync_interval_hours", 6),
            "share_country": cfg.get("ranking", {}).get("share_country", False),
            "country_code": cfg.get("ranking", {}).get("country_code", ""),
        })
        cfg.setdefault("main", {})["config_revision"] = 9
        revision = 9
        print("Migration v0.7.0: bounded assets, multi-asset companion, dashboard alerts and optional ranking added.")

    if revision < 10:
        # ConfigManager.load has already normalized known invalid CoinGecko IDs
        # such as BCH -> bitcoin-cash. Saving here persists the correction.
        cfg.setdefault("main", {})["config_revision"] = 10
        revision = 10
        print("Migration v0.7.1: Technical Sentinel serialization and CoinGecko BCH ID corrected.")

    if revision < 11:
        cfg.setdefault("connectivity", {}).setdefault("bluetooth_enabled", True)
        cfg.setdefault("main", {})["config_revision"] = 11
        revision = 11
        print("Migration v0.7.2: page Analyse séparée et interrupteur Bluetooth sûr ajoutés.")

    if revision < 12:
        # The NetworkManager profiles themselves store auto-connect and route
        # metrics. The installer upgrades existing profiles without deleting
        # a working bnep interface.
        cfg.setdefault("main", {})["config_revision"] = 12
        revision = 12
        print("Migration v0.7.3: basculement Wi-Fi/Bluetooth PAN et commandes radio sûres ajoutés.")

    manager.save(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
