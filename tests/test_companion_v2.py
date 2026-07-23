from cryptogotchi.db import Database
from cryptogotchi.personality import MicroBrain


def evaluated(change=2.5):
    return [{"coin": {"id": "bitcoin", "symbol": "BTC"}, "market": {"change_24h": change}, "metrics": {"15m": change, "24h": change, "volume_ratio": 2.2}}]


def test_companion_life_interaction_achievements_and_journal(tmp_path):
    db = Database(tmp_path / "brain.db")
    brain = MicroBrain(db)
    first = brain.observe("curious", evaluated(), "en", now=1_800_000_000, coin_count=5, network_type="bluetooth")
    assert first["level"] >= 1
    assert first["new_achievement"] is not None
    before = first["bond"]
    interaction = brain.interaction("pet", "en", now=1_800_000_010)
    assert interaction["bond"] > before
    entry = brain.force_journal("en", "CryptoGotchi", now=1_800_000_020)
    assert entry and "CryptoGotchi" in entry["text"]
    assert brain.journals(1)[0]["language"] == "en"
    keys = {item["key"] for item in brain.achievement_details("en") if item["unlocked"]}
    assert "first_watch" in keys
    assert "five_coins" in keys
    assert "traveler" in keys


def test_personality_sliders_change_message_shape(tmp_path):
    brain = MicroBrain(Database(tmp_path / "brain.db"))
    quiet = brain.observe("bullish", evaluated(3.2), "en", now=1_800_000_000, personality={"profile": "sage", "humor": 0, "verbosity": 0, "technical_level": 0})
    vivid = brain.observe("bullish", evaluated(3.2), "en", previous=quiet["message"], now=1_800_000_060, personality={"profile": "explorer", "humor": 100, "verbosity": 100, "technical_level": 100})
    assert quiet["message"] != vivid["message"]
    assert vivid["profile"] == "explorer"
