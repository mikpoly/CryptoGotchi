from cryptogotchi.config import ConfigManager
from cryptogotchi.db import Database
from cryptogotchi.market import MarketWorker


def test_worker_with_fake_market(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["coins"] = [cfg["coins"][0]]
    cfg["coins"][0]["drop_24h"] = 5.0
    cfg["coins"][0]["rise_24h"] = 0.0
    manager.save(cfg)
    db = Database(tmp_path / "data.db")
    worker = MarketWorker(manager, db)

    class FakeProvider:
        def update_config(self, config):
            pass
        def fetch_markets(self, coin_ids, fiat):
            return [{
                "id": "bitcoin", "symbol": "BTC", "name": "Bitcoin",
                "price": 50000.0, "volume": 1000.0, "market_cap": 1.0,
                "change_24h": -6.0,
            }]

    worker.provider = FakeProvider()
    worker.notifiers.dispatch = lambda alert: [{"channel": "fake", "ok": True}]
    worker.display.update = lambda status: None
    worker.run_once()
    status = worker.status()
    assert status["online"] is True
    assert status["coins"][0]["symbol"] == "BTC"
    assert "dropped" in status["message"]
    assert db.latest_alerts(1)[0]["rule"] == "drop_24h"
