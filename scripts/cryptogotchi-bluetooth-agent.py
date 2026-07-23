#!/usr/bin/env python3
"""Restricted BlueZ Agent1 for CryptoGotchi.

The agent only authorizes pairing while the web UI/helper has opened a short
pairing window in /run/cryptogotchi-bluetooth-pairing. This supports the
numeric-comparison flow used by modern Android phones and iPhones while
avoiding a permanently open pairing agent.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

BLUEZ = "org.bluez"
AGENT_IFACE = "org.bluez.Agent1"
AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
AGENT_PATH = "/org/cryptogotchi/agent"
WINDOW_FILE = Path("/run/cryptogotchi-bluetooth-pairing.json")


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


def _address_from_path(device: str) -> str:
    marker = "/dev_"
    if marker not in device:
        return ""
    return device.rsplit(marker, 1)[1].replace("_", ":").upper()


def _allowed(device: str) -> bool:
    try:
        data = json.loads(WINDOW_FILE.read_text(encoding="utf-8"))
        expires = int(data.get("expires", 0))
        allowed = str(data.get("address", "")).upper()
    except (OSError, ValueError, TypeError):
        return False
    if expires < int(time.time()):
        return False
    address = _address_from_path(device)
    return allowed in {"*", address}


def _is_paired(device: str) -> bool:
    try:
        bus = dbus.SystemBus()
        props = dbus.Interface(bus.get_object(BLUEZ, device), "org.freedesktop.DBus.Properties")
        return bool(props.Get("org.bluez.Device1", "Paired"))
    except dbus.DBusException:
        return False


def _require_allowed(device: str) -> None:
    if not _allowed(device):
        raise Rejected("CryptoGotchi pairing mode is not active for this device")


def _require_allowed_or_paired(device: str) -> None:
    if not _allowed(device) and not _is_paired(device):
        raise Rejected("Device is neither paired nor in the active pairing window")


class Agent(dbus.service.Object):
    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Release(self) -> None:
        return None

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device: str) -> str:
        _require_allowed(device)
        return "0000"

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device: str, pincode: str) -> None:
        _require_allowed(device)
        print(f"PIN for {_address_from_path(device)}: {pincode}", flush=True)

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device: str) -> dbus.UInt32:
        _require_allowed(device)
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_IFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device: str, passkey: int, entered: int) -> None:
        _require_allowed(device)
        print(f"Passkey for {_address_from_path(device)}: {int(passkey):06d} ({int(entered)} entered)", flush=True)

    @dbus.service.method(AGENT_IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device: str, passkey: int) -> None:
        _require_allowed(device)
        print(f"Confirming pairing for {_address_from_path(device)} passkey {int(passkey):06d}", flush=True)

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device: str) -> None:
        _require_allowed_or_paired(device)

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device: str, uuid: str) -> None:
        # Service authorization is restricted to paired devices. BlueZ only
        # calls this after authentication; no new pairing is opened here.
        if not _is_paired(device):
            raise Rejected("Device is not paired")

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Cancel(self) -> None:
        return None


def main() -> int:
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    agent = Agent(bus, AGENT_PATH)
    manager = dbus.Interface(bus.get_object(BLUEZ, "/org/bluez"), AGENT_MANAGER_IFACE)
    try:
        manager.UnregisterAgent(AGENT_PATH)
    except dbus.DBusException:
        pass
    manager.RegisterAgent(AGENT_PATH, "DisplayYesNo")
    manager.RequestDefaultAgent(AGENT_PATH)
    print("CryptoGotchi Bluetooth agent ready", flush=True)
    loop = GLib.MainLoop()
    # Keep both objects strongly referenced for the lifetime of the service.
    _ = agent
    loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
