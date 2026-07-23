from cryptogotchi.db import Database
from cryptogotchi.personality import MicroBrain


def test_microbrain_is_local_and_remembers(tmp_path):
    db = Database(tmp_path / "brain.db")
    evaluated = [{
        "coin": {"id": "bitcoin", "symbol": "BTC"},
        "metrics": {"15m": 2.4, "24h": 4.0, "volume_ratio": 2.2},
    }]
    brain = MicroBrain(db)
    first = brain.observe("bullish", evaluated, profile="sage", now=1_800_000_000)
    second = brain.observe("bullish", evaluated, profile="sage", now=1_800_000_060, previous=first["message"])
    assert first["engine"] == "micro-brain-v2"
    assert first["is_llm"] is False
    assert second["state_streak"] == 2
    assert first["leader"] == "BTC" and second["leader"] == "BTC"
    assert second["observations"] == 2
