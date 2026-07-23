from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any


MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _split_nmcli(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def _run(command: list[str], timeout: int = 8, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _normalize_connection_type(connection_type: str) -> str:
    return {
        "802-11-wireless": "wifi",
        "802-3-ethernet": "ethernet",
        "bluetooth": "bluetooth",
    }.get(connection_type, connection_type)


def active_connections() -> list[dict[str, Any]]:
    """Return NetworkManager connections with their real device names.

    This intentionally does not guess which connection carries Internet. That
    decision is made by :func:`active_connection_info` from the kernel route.
    """
    try:
        result = _run(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    connections: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = _split_nmcli(line)
        if len(parts) < 3 or not parts[2] or parts[1] in {"loopback", "bridge"}:
            continue
        connections.append(
            {
                "name": parts[0],
                "type": _normalize_connection_type(parts[1]),
                "raw_type": parts[1],
                "device": parts[2],
            }
        )
    return connections


def _internet_route_device() -> str | None:
    try:
        result = _run(["ip", "-4", "route", "get", "1.1.1.1"], timeout=4)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\bdev\s+(\S+)", result.stdout)
    return match.group(1) if match else None


def active_connection_info() -> dict[str, Any]:
    """Describe the connection actually selected by the Linux route table.

    Older versions preferred Bluetooth merely because a PAN profile was active,
    even while the default route still used Wi-Fi. The dashboard now follows
    ``ip route get 1.1.1.1`` and lists other active links as standby.
    """
    connections = active_connections()
    route_device = _internet_route_device()
    selected = next((item for item in connections if item["device"] == route_device), None)
    if selected is None and connections:
        priorities = {"wifi": 80, "ethernet": 70, "bluetooth": 60}
        selected = max(connections, key=lambda item: priorities.get(str(item.get("type")), 20))

    info: dict[str, Any] = {
        "name": None,
        "type": "none",
        "device": route_device,
        "metered": False,
        "metered_raw": "unknown",
        "route_device": route_device,
        "all": connections,
        "standby": [],
    }
    if selected is None:
        return info

    info.update({"name": selected["name"], "type": selected["type"], "device": selected["device"]})
    info["standby"] = [item for item in connections if item["device"] != selected["device"]]
    try:
        metered = _run(
            ["nmcli", "-g", "GENERAL.METERED", "device", "show", str(selected["device"])],
            timeout=4,
        ).stdout.strip().lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        metered = "unknown"
    info["metered_raw"] = metered or "unknown"
    info["metered"] = metered in {"yes", "guess-yes", "1", "true"}
    return info


def economy_state(config: dict[str, Any], connection: dict[str, Any] | None = None) -> dict[str, Any]:
    connection = connection or active_connection_info()
    section = config.get("connectivity", {})
    mode = str(section.get("data_saver_mode", "auto")).lower()
    reasons: list[str] = []
    active = mode == "on"
    if active:
        reasons.append("mode manuel")
    elif mode == "auto":
        if bool(section.get("auto_on_bluetooth", True)) and connection.get("type") == "bluetooth":
            active = True
            reasons.append("partage Bluetooth")
        if bool(section.get("auto_on_metered", True)) and connection.get("metered"):
            active = True
            reasons.append("connexion mesurée")
    return {
        "mode": mode,
        "active": active,
        "reason": ", ".join(reasons) if reasons else "connexion normale",
        "connection": connection,
        "refresh_seconds": max(60, int(section.get("economy_refresh_seconds", 300))) if active else max(30, int(config.get("main", {}).get("refresh_seconds", 60))),
        "allow_history_backfill": not active or bool(section.get("history_backfill_in_economy", False)),
        "allow_public_posts": not active or bool(section.get("public_posts_in_economy", False)),
        "allow_external_ai": not active or bool(section.get("external_ai_in_economy", False)),
    }


@dataclass
class BluetoothDevice:
    address: str
    name: str
    paired: bool = False
    connected: bool = False
    trusted: bool = False
    pan_active: bool = False
    pan_device: str | None = None
    pan_ipv4: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "paired": self.paired,
            "connected": self.connected,
            "trusted": self.trusted,
            "pan_active": self.pan_active,
            "pan_device": self.pan_device,
            "pan_ipv4": self.pan_ipv4,
        }


class BluetoothManager:
    HELPER = "/usr/local/sbin/cryptogotchi-bluetooth-helper"

    def available(self) -> bool:
        """Return true only when BlueZ has a usable controller."""
        for attempt in range(4):
            try:
                result = _run(["bluetoothctl", "show"], timeout=5)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return False
            if result.returncode == 0 and "Controller" in result.stdout:
                return True
            if attempt < 3:
                time.sleep(0.5)
        return False

    def _helper_path(self) -> str:
        if os.path.isfile(self.HELPER) and os.access(self.HELPER, os.X_OK):
            return self.HELPER
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "cryptogotchi-bluetooth-helper"))

    def _privileged_simple(self, action: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        command = ["sudo", "-n", self._helper_path(), action]
        try:
            result = _run(command, timeout=timeout)
        except FileNotFoundError as exc:
            raise RuntimeError("The privileged connectivity helper is not installed. Re-run scripts/install.sh.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Connectivity operation timed out.") from exc
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Connectivity operation failed").strip()
            raise RuntimeError(message[-1200:])
        return result

    def powered(self) -> bool:
        try:
            result = _run(["bluetoothctl", "show"], timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and any(
            line.strip() == "Powered: yes" for line in result.stdout.splitlines()
        )

    def wifi_powered(self) -> bool:
        try:
            result = _run(["nmcli", "radio", "wifi"], timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and result.stdout.strip().lower() == "enabled"

    def set_enabled(self, enabled: bool) -> str:
        action = "power-on" if enabled else "power-off"
        result = self._privileged_simple(action, timeout=35)
        return (result.stdout or result.stderr or "").strip()

    def set_wifi_enabled(self, enabled: bool) -> str:
        action = "wifi-on" if enabled else "wifi-off"
        result = self._privileged_simple(action, timeout=35)
        return (result.stdout or result.stderr or "").strip()

    def apply_configured_state(self, enabled: bool) -> None:
        try:
            self.set_enabled(bool(enabled))
        except RuntimeError:
            # Hardware state must never prevent the web service from starting.
            return

    def _privileged(self, action: str, address: str, timeout: int = 80) -> subprocess.CompletedProcess[str]:
        address = self.validate_address(address)
        command = ["sudo", "-n", self._helper_path(), action, address]
        try:
            result = _run(command, timeout=timeout)
        except FileNotFoundError as exc:
            raise RuntimeError("The privileged Bluetooth helper is not installed. Re-run scripts/install.sh.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Bluetooth operation timed out. Keep the phone unlocked and Bluetooth visible.") from exc
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Bluetooth operation failed").strip()
            raise RuntimeError(message[-1200:])
        return result

    def prepare_pairing(self) -> str:
        result = self._privileged_simple("prepare", timeout=20)
        return (result.stdout or "").strip()

    @staticmethod
    def validate_address(address: str) -> str:
        address = address.strip().upper()
        if not MAC_RE.fullmatch(address):
            raise ValueError("Adresse Bluetooth invalide")
        return address

    @staticmethod
    def profile_name(address: str) -> str:
        return f"CryptoGotchi Bluetooth {address.replace(':', '')[-6:]}"

    def _pan_state(self, address: str) -> tuple[bool, str | None, str | None]:
        profile = self.profile_name(address)
        try:
            result = _run(
                ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False, None, None
        device: str | None = None
        for line in result.stdout.splitlines():
            parts = _split_nmcli(line)
            if len(parts) >= 3 and parts[0] == profile and parts[1] == "bluetooth" and parts[2]:
                device = parts[2]
                break
        if not device:
            return False, None, None
        try:
            ipv4 = _run(["nmcli", "-g", "IP4.ADDRESS", "device", "show", device], timeout=4).stdout.strip().splitlines()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            ipv4 = []
        return bool(ipv4), device, ipv4[0] if ipv4 else None

    def _device_info(self, address: str) -> BluetoothDevice:
        result = _run(["bluetoothctl", "info", address], timeout=5)
        name = address
        paired = connected = trusted = False
        for raw in result.stdout.splitlines():
            line = raw.strip()
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip() or address
            elif line.startswith("Alias:") and name == address:
                name = line.split(":", 1)[1].strip() or address
            elif line.startswith("Paired:"):
                paired = line.endswith("yes")
            elif line.startswith("Connected:"):
                connected = line.endswith("yes")
            elif line.startswith("Trusted:"):
                trusted = line.endswith("yes")
        pan_active, pan_device, pan_ipv4 = self._pan_state(address)
        return BluetoothDevice(
            address,
            name,
            paired,
            connected,
            trusted,
            pan_active,
            pan_device,
            pan_ipv4,
        )

    def scan(self, seconds: int = 12) -> list[dict[str, Any]]:
        seconds = max(5, min(25, int(seconds)))
        if not self.available():
            raise RuntimeError("Bluetooth/BlueZ n'est pas disponible")
        _run(["bluetoothctl", "power", "on"], timeout=8)
        _run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], timeout=seconds + 5)
        result = _run(["bluetoothctl", "devices"], timeout=6)
        devices: list[BluetoothDevice] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            if not line.startswith("Device "):
                continue
            parts = line.split(" ", 2)
            if len(parts) < 3 or not MAC_RE.fullmatch(parts[1]):
                continue
            address = parts[1].upper()
            if address in seen:
                continue
            seen.add(address)
            device = self._device_info(address)
            if device.name == address:
                device.name = parts[2].strip() or address
            devices.append(device)
        devices.sort(key=lambda item: (not item.pan_active, not item.paired, item.name.lower()))
        return [device.as_dict() for device in devices[:30]]

    def pair(self, address: str) -> dict[str, Any]:
        address = self.validate_address(address)
        self._privileged("pair", address, timeout=85)
        device = self._device_info(address)
        if not device.paired:
            raise RuntimeError("Pairing completed without a paired device. Keep the phone unlocked and retry.")
        return device.as_dict()

    def connect_pan(self, address: str) -> dict[str, Any]:
        address = self.validate_address(address)
        result = self._privileged("connect", address, timeout=230)
        device = self._device_info(address)
        if not device.pan_active:
            raise RuntimeError("Bluetooth PAN command ended without an active bnep interface.")
        return {
            "profile": self.profile_name(address),
            "device": device.as_dict(),
            "details": (result.stdout or "").strip()[-1600:],
        }

    def diagnostics(self, address: str) -> str:
        address = self.validate_address(address)
        result = self._privileged("diagnose", address, timeout=50)
        return (result.stdout or result.stderr or "No diagnostic output").strip()[-9000:]

    def disconnect(self, address: str) -> None:
        address = self.validate_address(address)
        self._privileged("disconnect", address, timeout=35)

    def remove(self, address: str) -> None:
        address = self.validate_address(address)
        self._privileged("remove", address, timeout=35)
