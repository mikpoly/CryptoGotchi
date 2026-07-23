from cryptogotchi.config import ConfigManager


def test_config_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    manager = ConfigManager(path)
    cfg = manager.load()
    assert cfg["main"]["name"] == "CryptoGotchi"
    assert cfg["main"]["language"] == "en"
    assert cfg["main"]["config_revision"] == 12
    assert cfg["ai"]["mode"] == "local"
    cfg["main"]["name"] = "TestGotchi"
    manager.save(cfg)
    assert manager.load()["main"]["name"] == "TestGotchi"


def test_public_snapshot_masks_secrets_and_accepts_pause_flag(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["notifications"]["paused"] = True
    cfg["notifications"]["telegram"]["bot_token"] = "secret"
    manager.save(cfg)
    snapshot = manager.public_snapshot()
    assert snapshot["notifications"]["paused"] is True
    assert snapshot["notifications"]["telegram"]["bot_token"] == "***"
