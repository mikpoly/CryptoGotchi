from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from typing import Any


def _run(command: list[str], timeout: int = 3) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return (result.stdout or "").strip()
    except Exception:
        return ""



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

def local_ip() -> str | None:
    # Ne transmet aucune donnée: le socket UDP sert uniquement à choisir l'interface locale.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        address = str(sock.getsockname()[0])
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    finally:
        sock.close()
    # Sans route Internet (premier démarrage USB), conserver une adresse locale utile.
    for address in _run(["hostname", "-I"], timeout=2).split():
        if address.count(".") == 3 and not address.startswith(("127.", "169.254.")):
            return address
    return None


def cpu_temperature() -> float | None:
    paths = [
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/devices/virtual/thermal/thermal_zone0/temp"),
    ]
    for path in paths:
        try:
            return float(path.read_text(encoding="utf-8").strip()) / 1000.0
        except (OSError, ValueError):
            continue
    return None


def memory_percent() -> float | None:
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        return ((total - available) / total * 100.0) if total else None
    except (OSError, ValueError):
        return None


def uptime_human() -> str | None:
    try:
        seconds = int(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0]))
    except (OSError, ValueError, IndexError):
        return None
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days}j {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def wifi_info() -> tuple[str | None, int | None]:
    output = _run(["nmcli", "-t", "-f", "active,ssid,signal", "dev", "wifi"], timeout=4)
    for line in output.splitlines():
        parts = _split_nmcli(line)
        if len(parts) >= 3 and parts[0] == "yes":
            try:
                signal = int(parts[-1])
            except ValueError:
                signal = None
            return ":".join(parts[1:-1]) or None, signal
    # Fallback iwgetid/iwconfig pour les installations sans NetworkManager.
    ssid = _run(["iwgetid", "-r"], timeout=2) or None
    return ssid, None


def collect_system_info() -> dict[str, Any]:
    ssid, signal = wifi_info()
    return {
        "hostname": socket.gethostname(),
        "ip": local_ip(),
        "wifi_ssid": ssid,
        "wifi_signal": signal,
        "cpu_temp_c": cpu_temperature(),
        "memory_percent": memory_percent(),
        "uptime": uptime_human(),
        "load_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
    }
