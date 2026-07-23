import pytest

from cryptogotchi.config import default_config
from cryptogotchi.connectivity import BluetoothManager, economy_state


def test_economy_auto_on_bluetooth():
    cfg = default_config()
    state = economy_state(cfg, {"type": "bluetooth", "metered": True, "name": "Phone", "device": "bnep0"})
    assert state["active"] is True
    assert state["refresh_seconds"] == 300
    assert state["allow_history_backfill"] is False
    assert state["allow_public_posts"] is False


def test_economy_off_ignores_metered():
    cfg = default_config()
    cfg["connectivity"]["data_saver_mode"] = "off"
    state = economy_state(cfg, {"type": "bluetooth", "metered": True})
    assert state["active"] is False
    assert state["refresh_seconds"] == cfg["main"]["refresh_seconds"]


def test_bluetooth_address_validation_and_profile():
    manager = BluetoothManager()
    assert manager.validate_address("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
    assert manager.profile_name("AA:BB:CC:DD:EE:FF") == "CryptoGotchi Bluetooth DDEEFF"
    with pytest.raises(ValueError):
        manager.validate_address("not-a-mac")


def test_bluetooth_pair_uses_privileged_helper(monkeypatch):
    manager = BluetoothManager()
    calls = []
    monkeypatch.setattr(manager, "_privileged", lambda action, address, timeout=80: calls.append((action, address, timeout)))
    monkeypatch.setattr(manager, "_device_info", lambda address: __import__('cryptogotchi.connectivity', fromlist=['BluetoothDevice']).BluetoothDevice(address, "Phone", True, False, True))
    result = manager.pair("aa:bb:cc:dd:ee:ff")
    assert calls == [("pair", "AA:BB:CC:DD:EE:FF", 85)]
    assert result["paired"] is True


def test_prepare_pairing_uses_privileged_helper(monkeypatch):
    manager = BluetoothManager()
    class Result:
        returncode = 0
        stdout = "visible"
        stderr = ""
    calls = []
    monkeypatch.setattr("cryptogotchi.connectivity._run", lambda command, timeout=10: (calls.append((command, timeout)) or Result()))
    assert manager.prepare_pairing() == "visible"
    assert calls[0][0][-1] == "prepare"


def test_bluetooth_power_toggle_never_targets_wifi(monkeypatch):
    manager = BluetoothManager()
    calls = []

    class Result:
        returncode = 0
        stdout = "Bluetooth disabled; Wi-Fi was not modified"
        stderr = ""

    monkeypatch.setattr("cryptogotchi.connectivity._run", lambda command, timeout=10, input_text=None: (calls.append(command) or Result()))
    manager.set_enabled(False)
    flattened = " ".join(calls[0]).lower()
    assert "power-off" in flattened
    assert "wifi" not in flattened
