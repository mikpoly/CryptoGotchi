#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from cryptogotchi.config import ConfigManager
from cryptogotchi.db import Database
from cryptogotchi.market import MarketWorker


def main() -> None:
    now = int(time.time())
    with tempfile.TemporaryDirectory(prefix="cryptogotchi-preflight-") as tmp:
        root = Path(tmp)
        manager = ConfigManager(root / "config.toml")
        cfg = manager.load()
        cfg["main"].update({"language": "fr", "fiat": "eur", "history_hours": 72})
        cfg["display"]["type"] = "virtual"
        cfg["coins"] = [
            {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "enabled": True, "favorite": True},
            {"id": "ethereum", "symbol": "ETH", "name": "Ethereum", "enabled": True},
        ]
        manager.save(cfg)
        db = Database(root / "cryptogotchi.db")
        for coin_id, base in (("bitcoin", 100.0), ("ethereum", 50.0)):
            for index in range(72):
                price = base + ((index % 12) - 6) * 0.15 + max(0, index - 64) * 0.12
                db.add_sample(coin_id, now - (71 - index) * 60, price, 1000 + index * 5, 1.0, "eur", "coingecko")
        worker = MarketWorker(manager, db)
        worker._set_status(
            online=True,
            state="calm",
            coins=[
                {
                    "id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "price": 101.4,
                    "fiat": "eur", "source": "coingecko", "asset_kind": "crypto", "trading_mode": "24x7",
                    "metrics": {"5m": 0.4, "15m": 0.9, "1h": 1.5, "24h": 2.1, "volume_ratio": 1.3},
                },
                {
                    "id": "ethereum", "symbol": "ETH", "name": "Ethereum", "price": 50.6,
                    "fiat": "eur", "source": "coingecko", "asset_kind": "crypto", "trading_mode": "24x7",
                    "metrics": {"5m": -0.2, "15m": -0.5, "1h": 0.2, "24h": 0.8, "volume_ratio": 1.1},
                },
            ],
        )
        worker.ask_selected_coins(["bitcoin", "ethereum"])
        encoded = json.dumps(worker.status(), ensure_ascii=False)
        companion = worker.status().get("companion") or {}
        analyses = companion.get("technical_analysis") or []
        if not analyses:
            raise RuntimeError("Technical analysis is missing")
        for analysis in analyses:
            frames = analysis.get("timeframes") or {}
            if set(frames) != {"15m", "1h", "4h"}:
                raise RuntimeError("Expected 15m, 1h and 4h timeframes")
            if analysis.get("verdict") not in {"buy", "sell", "wait"}:
                raise RuntimeError("Invalid companion verdict")
        if "support_text" not in encoded or "resistance_text" not in encoded:
            raise RuntimeError("Technical levels are missing")
        print("CryptoGotchi 15m/1h/4h analysis preflight OK")


if __name__ == "__main__":
    main()
