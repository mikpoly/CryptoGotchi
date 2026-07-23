from pathlib import Path

from cryptogotchi.config import ConfigManager


def test_v072_defaults_are_safe(tmp_path):
    cfg = ConfigManager(tmp_path / "config.toml").load()
    assert cfg["main"]["config_revision"] == 12
    assert cfg["connectivity"]["bluetooth_enabled"] is True


def test_bluetooth_helper_does_not_toggle_all_radios():
    helper = Path("scripts/cryptogotchi-bluetooth-helper").read_text(encoding="utf-8")
    assert "nmcli radio all off" not in helper
    assert "nmcli radio all on" not in helper
    assert "rfkill block bluetooth" in helper
    assert "Wi-Fi was not modified" in helper


def test_install_script_does_not_disable_wifi_or_ssh():
    installer = Path("scripts/install.sh").read_text(encoding="utf-8").lower()
    forbidden = (
        "rfkill block wifi",
        "nmcli radio wifi off",
        "systemctl disable ssh",
        "systemctl stop ssh",
    )
    for token in forbidden:
        assert token not in installer
