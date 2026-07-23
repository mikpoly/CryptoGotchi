import time
from cryptogotchi.alerts import AlertEngine
from cryptogotchi.db import Database


def test_pct_change():
    assert AlertEngine.pct_change(90, 100) == -10
    assert AlertEngine.pct_change(110, 100) == 10


def test_drop_alert(tmp_path):
    db = Database(tmp_path / "test.db")
    engine = AlertEngine(db)
    now = int(time.time())
    db.add_sample("bitcoin", now - 301, 100, 1000, 0)
    db.add_sample("bitcoin", now, 95, 1000, -5)
    coin = {
        "id": "bitcoin", "symbol": "BTC", "drop_5m": 2, "rise_5m": 2,
        "drop_15m": 0, "rise_15m": 0, "drop_1h": 0, "rise_1h": 0,
        "drop_24h": 0, "rise_24h": 0, "volume_multiplier": 0,
        "new_high_24h": False, "new_low_24h": False,
        "cooldown_minutes": 30, "social_post": False,
    }
    market = {"id": "bitcoin", "price": 95, "volume": 1000, "change_24h": -5}
    metrics, alerts = engine.evaluate_coin(market, coin, now)
    assert round(metrics["5m"], 2) == -5
    assert any(a["rule"] == "drop_5m" for a in alerts)


def test_provider_one_hour_change_is_authoritative(tmp_path):
    db = Database(tmp_path / "provider.db")
    engine = AlertEngine(db)
    now = int(time.time())
    # Deliberately contaminated local sample: provider 1h must win.
    db.add_sample("bitcoin", now - 3600, 100.0, 1000, 0, "usd", "coingecko")
    market = {
        "id": "bitcoin", "price": 115.0, "volume": 1000,
        "change_1h": 0.42, "change_24h": -0.1,
        "fiat": "usd", "source": "coingecko",
    }
    metrics = engine.metrics_for_coin(market, now)
    assert metrics["1h"] == 0.42
    assert metrics["1h_source"] == "provider"
    assert round(metrics["1h_local"], 2) == 15.0
    assert metrics["quality_warning"]
