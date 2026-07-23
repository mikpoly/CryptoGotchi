from __future__ import annotations

import time

from cryptogotchi.alerts import AlertEngine
from cryptogotchi.config import ConfigManager
from cryptogotchi.db import Database
from cryptogotchi.market import GoldApiProvider


def test_currency_streams_are_never_mixed(tmp_path):
    db = Database(tmp_path / "market.db")
    engine = AlertEngine(db)
    now = int(time.time())
    # Legacy/EUR observation must never become the reference for a USD move.
    db.add_sample("bitcoin", now - 900, 100.0, 1000, 0, "eur", "coingecko")
    db.add_sample("bitcoin", now, 114.0, 1000, 0, "usd", "coingecko")
    metrics = engine.metrics_for_coin({"id": "bitcoin", "price": 114.0, "volume": 1000, "fiat": "usd", "source": "coingecko"}, now)
    assert metrics["15m"] is None

    db.add_sample("bitcoin", now - 900, 110.0, 1000, 0, "usd", "coingecko")
    metrics = engine.metrics_for_coin({"id": "bitcoin", "price": 114.0, "volume": 1000, "fiat": "usd", "source": "coingecko"}, now)
    assert round(metrics["15m"], 2) == 3.64


def test_closed_or_stale_markets_never_emit_threshold_alerts(tmp_path):
    db = Database(tmp_path / "market.db")
    engine = AlertEngine(db)
    now = int(time.time())
    db.add_sample("spot-xau", now - 900, 2200, None, None, "usd", "gold_api")
    coin = {
        "id": "spot-xau", "symbol": "XAU", "drop_5m": 1, "rise_5m": 1,
        "drop_15m": 1, "rise_15m": 1, "drop_1h": 1, "rise_1h": 1,
        "drop_24h": 1, "rise_24h": 1, "volume_multiplier": 0,
        "new_high_24h": False, "new_low_24h": False, "cooldown_minutes": 30,
        "social_post": False,
    }
    market = {"id": "spot-xau", "price": 2500, "volume": 0, "change_24h": None, "fiat": "usd", "source": "gold_api", "market_status": "closed"}
    metrics, alerts = engine.evaluate_coin(market, coin, now)
    assert metrics["15m"] is not None
    assert alerts == []


def test_v04_mistaken_gold_and_spcx_are_migrated(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["coins"] = [
        {"id": "gold-8", "symbol": "XAU", "name": "Gold", "enabled": True},
        {"id": "spacex-token", "symbol": "SPCX", "name": "SpaceX • Robinhood Token", "enabled": True},
    ]
    manager.save(cfg)
    migrated = manager.load()["coins"]
    gold = migrated[0]
    spcx = migrated[1]
    assert gold["id"] == "spot-xau"
    assert gold["source"] == "gold_api"
    assert gold["asset_kind"] == "commodity"
    assert gold["include_in_market_mood"] is False
    assert spcx["asset_kind"] == "tokenized_asset"
    assert spcx["trading_mode"] == "24x7"
    assert spcx["include_in_market_mood"] is False


class _Response:
    content = b'{"currency":"USD","name":"Gold","price":2412.5,"symbol":"XAU","updatedAt":"2026-07-23T07:00:00Z"}'
    def raise_for_status(self):
        return None
    def json(self):
        return {"currency": "USD", "name": "Gold", "price": 2412.5, "symbol": "XAU", "updatedAt": "2026-07-23T07:00:00Z"}


class _Session:
    def __init__(self):
        self.urls = []
    def get(self, url, *args, **kwargs):
        self.urls.append(url)
        return _Response()


def test_gold_provider_parses_real_spot_quote(monkeypatch):
    cfg = ConfigManager.__new__(ConfigManager)  # only to avoid unrelated filesystem setup
    del cfg
    provider = GoldApiProvider({"provider": {"gold_api_base_url": "https://api.gold-api.com", "timeout_seconds": 10, "freshness_seconds": 99999999}})
    provider.session = _Session()
    monkeypatch.setattr("cryptogotchi.market.time.time", lambda: 1784793600)
    rows = provider.fetch_markets([{"id": "spot-xau", "symbol": "XAU", "provider_symbol": "XAU", "name": "Gold Spot"}], "usd")
    assert provider.session.urls == ["https://api.gold-api.com/price/XAU"]
    assert rows[0]["price"] == 2412.5
    assert rows[0]["unit"] == "troy_ounce"
    assert rows[0]["source"] == "gold_api"


class _BadGoldSession:
    def get(self, *args, **kwargs):
        class Response:
            content = b'{"price":0.000051}'
            def raise_for_status(self): return None
            def json(self): return {"price": 0.000051, "symbol": "XAU"}
        return Response()


def test_implausible_inverse_gold_quote_is_rejected():
    provider = GoldApiProvider({"provider": {"gold_api_base_url": "https://api.gold-api.com", "timeout_seconds": 10}})
    provider.session = _BadGoldSession()
    rows = provider.fetch_markets([{"id": "spot-xau", "symbol": "XAU", "provider_symbol": "XAU"}], "usd")
    assert rows == []


def test_legacy_database_is_migrated_before_stream_index_is_created(tmp_path):
    """Regression test for the v0.6.0 startup crash on upgraded devices.

    v0.4-era databases have a price_samples table without quote_currency and
    source. The index referencing those columns must only be created after the
    ALTER TABLE migration has completed.
    """
    import sqlite3

    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE price_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin_id TEXT NOT NULL,
                ts INTEGER NOT NULL,
                price REAL NOT NULL,
                volume REAL,
                change_24h REAL
            );
            INSERT INTO price_samples(coin_id, ts, price, volume, change_24h)
            VALUES('bitcoin', 1, 100.0, 1000.0, 0.0);
            """
        )

    db = Database(db_path)
    with db.connect() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(price_samples)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(price_samples)")}
        sample = conn.execute(
            "SELECT coin_id, quote_currency, source FROM price_samples"
        ).fetchone()

    assert {"quote_currency", "source"}.issubset(columns)
    assert "idx_price_coin_quote_source_ts" in indexes
    assert sample[0] == "bitcoin"
    assert sample[1] == ""
    assert sample[2] == "coingecko"
