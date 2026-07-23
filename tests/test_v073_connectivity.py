from pathlib import Path

from cryptogotchi import connectivity
from cryptogotchi.connectivity import BluetoothManager, active_connection_info


class Result:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_active_connection_follows_kernel_route(monkeypatch):
    def fake_run(command, timeout=8, input_text=None):
        joined = " ".join(command)
        if "connection show --active" in joined:
            return Result(
                "Home WiFi:wifi:wlan0\n"
                "CryptoGotchi Bluetooth 50D96E:bluetooth:bnep0\n"
            )
        if command[:4] == ["ip", "-4", "route", "get"]:
            return Result("1.1.1.1 via 192.0.2.1 dev wlan0 src 192.0.2.20\n")
        if "GENERAL.METERED" in joined:
            return Result("no\n")
        return Result()

    monkeypatch.setattr(connectivity, "_run", fake_run)
    info = active_connection_info()
    assert info["type"] == "wifi"
    assert info["device"] == "wlan0"
    assert info["standby"][0]["type"] == "bluetooth"
    assert info["standby"][0]["device"] == "bnep0"


def test_pan_state_is_not_the_same_as_bluez_connected(monkeypatch):
    manager = BluetoothManager()

    def fake_run(command, timeout=8, input_text=None):
        joined = " ".join(command)
        if command[:2] == ["bluetoothctl", "info"]:
            return Result("Name: Test Phone\nPaired: yes\nTrusted: yes\nConnected: yes\n")
        if "connection show --active" in joined:
            return Result("Home WiFi:wifi:wlan0\n")
        return Result()

    monkeypatch.setattr(connectivity, "_run", fake_run)
    device = manager._device_info("AA:BB:CC:DD:EE:FF")
    assert device.connected is True
    assert device.pan_active is False


def test_helper_preserves_working_pan_and_enables_autoconnect():
    helper = Path("scripts/cryptogotchi-bluetooth-helper").read_text(encoding="utf-8")
    connect_body = helper.split("connect_pan() {", 1)[1].split("diagnose_pan() {", 1)[0]
    assert "connection.autoconnect yes" in helper
    assert "ipv4.route-metric 750" in helper
    assert "if verify_pan" in connect_body
    assert 'bluetoothctl disconnect "$ADDRESS"' not in connect_body


def test_wifi_off_is_guarded_and_watchdog_installed():
    helper = Path("scripts/cryptogotchi-bluetooth-helper").read_text(encoding="utf-8")
    watcher = Path("scripts/cryptogotchi-connectivity-watch").read_text(encoding="utf-8")
    installer = Path("scripts/install.sh").read_text(encoding="utf-8")
    assert "a working Bluetooth PAN connection is required" in helper
    assert "pan_has_internet" in helper
    assert "Wi-Fi re-enabled because Bluetooth PAN is no longer active" in watcher
    assert "cryptogotchi-connectivity-watch.service" in installer
