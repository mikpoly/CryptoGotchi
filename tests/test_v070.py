import json
from pathlib import Path

from cryptogotchi.config import ConfigManager
from cryptogotchi.db import Database
from cryptogotchi.market import CoinGeckoProvider, MarketWorker
from cryptogotchi.ranking import RankingClient


class Response:
    status_code = 200
    content = b"{}"
    text = ""

    def __init__(self, data):
        self.data = data
        self.content = json.dumps(data).encode()

    def json(self):
        return self.data

    def raise_for_status(self):
        return None


def test_coingecko_market_request_is_bounded_and_explicit():
    manager = ConfigManager(Path("/tmp/nonexistent-cg-v070-config.toml"))
    provider = CoinGeckoProvider(manager.load())
    calls = []

    def fake_get(path, params):
        calls.append((path, params))
        rows = [
            {"id": coin_id, "symbol": coin_id[:3], "name": coin_id, "current_price": 1.0}
            for coin_id in params["ids"].split(",")
        ]
        return Response(rows)

    provider._get = fake_get
    rows = provider.fetch_markets(["bitcoin", "ethereum", "bitcoin"], "eur")
    assert [row["id"] for row in rows] == ["bitcoin", "ethereum"]
    assert calls[0][0] == "/coins/markets"
    assert calls[0][1]["per_page"] == 2
    assert calls[0][1]["page"] == 1


def test_companion_web_selection_is_independent_from_lcd(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    db = Database(tmp_path / "db.sqlite")
    worker = MarketWorker(manager, db)
    worker._set_status(
        coins=[
            {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "metrics": {"15m": 1.2}, "change_24h": 2.0},
            {"id": "ethereum", "symbol": "ETH", "name": "Ethereum", "metrics": {"15m": -0.4}, "change_24h": -1.0},
        ],
        display={"coin_index": 0},
    )
    worker.set_companion_selection(["ethereum"])
    assert worker.display_coin_status()["id"] == "bitcoin"
    assert worker.selected_coin_status()["id"] == "ethereum"
    text = worker.ask_selected_coins(["bitcoin", "ethereum"])
    assert "BTC" in text and "ETH" in text
    assert worker.companion_selected_ids() == ["bitcoin", "ethereum"]
    # Regression: technical Zone objects must never leak into the public status.
    json.dumps(worker.status(), ensure_ascii=False)

    # The LCD may analyze its own currently displayed asset without replacing
    # the independent web selection saved by the user.
    worker.ask_selected_coin()
    assert worker.companion_selected_ids() == ["bitcoin", "ethereum"]


def test_active_asset_limit_hard_caps_at_100(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["main"]["max_active_assets"] = 1000
    manager.save(cfg)
    assert MarketWorker.active_asset_limit(manager.load()) == 100


def test_ranking_payload_is_opt_in_and_privacy_minimal(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    db = Database(tmp_path / "db.sqlite")
    client = RankingClient(manager, db)
    status = {
        "coins": [{"id": "bitcoin", "price": 50000, "data_note": "private-ish"}],
        "companion": {"level": 4, "xp": 320, "observations": 90, "achievement_count": 3},
        "network": {"connection": {"name": "My phone"}},
        "last_alert": {"message": "secret alert"},
    }
    payload = client.build_payload(status)
    assert payload["level"] == 4
    assert payload["tracked_assets"] == 1
    encoded = json.dumps(payload)
    for forbidden in ("price", "network", "phone", "alert", "wallet", "secret"):
        assert forbidden not in encoded.lower()
    assert client.should_sync() is False


def test_bluetooth_helper_uses_unbound_panu_profile_and_retries():
    helper = Path("scripts/cryptogotchi-bluetooth-helper").read_text(encoding="utf-8")
    assert "bluetooth.type panu" in helper
    assert "ifname '*'" not in helper
    assert "connection.autoconnect yes" in helper
    assert "for attempt in 1 2" in helper
    assert "journalctl -u NetworkManager" in helper
    assert "ipv6.method disabled" in helper


def test_revision_nine_defaults_present(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    assert cfg["main"]["config_revision"] == 12
    assert cfg["main"]["max_active_assets"] == 50
    assert cfg["notifications"]["dashboard"]["enabled"] is True
    assert cfg["ranking"]["enabled"] is False

def test_ranking_failure_has_retry_backoff(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["ranking"].update({
        "enabled": True,
        "endpoint_url": "https://community.example/ranking",
        "sync_interval_hours": 6,
    })
    manager.save(cfg)
    db = Database(tmp_path / "db.sqlite")
    client = RankingClient(manager, db)
    now = 1_800_000_000
    db.set_state("ranking:last_attempt_ts", now - 60)
    db.set_state("ranking:last_error", "offline")
    assert client.should_sync(now) is False
    assert client.should_sync(now + 15 * 60) is True



def test_revision_eight_migration_preserves_existing_secrets_and_assets(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "legacy.toml"
    manager = ConfigManager(path)
    cfg = manager.load()
    cfg["main"]["config_revision"] = 8
    cfg["main"].pop("max_active_assets", None)
    cfg["companion"].pop("manual_message_hold_seconds", None)
    cfg["companion"].pop("max_analysis_assets", None)
    cfg["notifications"].pop("dashboard", None)
    cfg.pop("ranking", None)
    cfg["notifications"]["telegram"]["bot_token"] = "keep-this-token"
    cfg["coins"].append({"id": "solana", "symbol": "SOL", "name": "Solana", "enabled": False})
    manager.save(cfg)

    subprocess.run([sys.executable, "scripts/migrate-config.py", str(path)], check=True)
    migrated = manager.load()
    assert migrated["main"]["config_revision"] == 12
    assert migrated["main"]["max_active_assets"] == 50
    assert migrated["notifications"]["telegram"]["bot_token"] == "keep-this-token"
    assert any(coin["id"] == "solana" and not coin["enabled"] for coin in migrated["coins"])
    assert migrated["ranking"]["enabled"] is False


def test_bch_symbol_is_migrated_to_coingecko_id(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["coins"].append({"id": "bch", "symbol": "BCH", "name": "Bitcoin Cash"})
    manager.save(cfg)
    loaded = manager.load()
    assert any(coin["id"] == "bitcoin-cash" for coin in loaded["coins"])
    assert not any(coin["id"] == "bch" for coin in loaded["coins"])
