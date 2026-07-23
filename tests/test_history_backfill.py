import time

from cryptogotchi.config import ConfigManager
from cryptogotchi.db import Database
from cryptogotchi.market import MarketWorker


def test_new_coin_history_is_backfilled_for_graph(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["coins"] = [cfg["coins"][0]]
    for key in ("drop_5m", "rise_5m", "drop_15m", "rise_15m", "drop_1h", "rise_1h", "drop_24h", "rise_24h"):
        cfg["coins"][0][key] = 0
    manager.save(cfg)
    db = Database(tmp_path / "data.db")
    worker = MarketWorker(manager, db)
    now = int(time.time())

    class FakeProvider:
        def update_config(self, config):
            pass
        def fetch_markets(self, coin_ids, fiat):
            return [{"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "price": 110.0, "volume": 1000.0, "market_cap": 1.0, "change_24h": 1.0, "fiat": fiat}]
        def fetch_history(self, coin_id, fiat, days=1):
            return [{"ts": now - (12-i)*300, "price": 100+i, "volume": 500+i} for i in range(12)]
        def consume_transfer_stats(self):
            return {"bytes": 2048, "requests": 2}

    worker.provider = FakeProvider()
    worker.notifiers.dispatch = lambda alert: []
    worker.display.update = lambda status: None
    worker.request_backfill("bitcoin")
    worker.run_once()
    coin = worker.status()["coins"][0]
    assert coin["sparkline_meta"]["ready"] is True
    assert coin["sparkline_meta"]["samples"] >= 12
    assert len(coin["sparkline"]) >= 12
    assert worker.status()["network"]["usage_today_bytes"] >= 2048
