from __future__ import annotations


def build_wifi_profile_commands(
    ssid: str,
    password: str,
    hidden: bool,
    security: str,
) -> list[tuple[list[str], int]]:
    """Construit les commandes nmcli sans shell pour un profil Wi-Fi complet."""
    profile_name = f"CryptoGotchi: {ssid}"
    modify = [
        "connection", "modify", profile_name,
        "connection.autoconnect", "yes",
        "connection.autoconnect-priority", "20",
        "802-11-wireless.hidden", "yes" if hidden else "no",
        "ipv4.method", "auto",
        "ipv6.method", "auto",
    ]
    if security != "open":
        modify += [
            "802-11-wireless-security.key-mgmt", security,
            "802-11-wireless-security.psk", password,
        ]
    return [
        (["connection", "delete", "id", profile_name], 20),
        ([
            "connection", "add", "type", "wifi", "ifname", "wlan0",
            "con-name", profile_name, "ssid", ssid,
        ], 45),
        (modify, 45),
        (["connection", "up", "id", profile_name, "ifname", "wlan0"], 55),
    ]
