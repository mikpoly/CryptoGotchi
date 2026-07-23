from cryptogotchi.wifi import build_wifi_profile_commands


def flattened(command):
    return " ".join(command)


def test_hidden_wpa_profile_sets_hidden_key_mgmt_and_psk():
    commands = build_wifi_profile_commands("MaisonCachee", "secret-wifi", True, "wpa-psk")
    assert len(commands) == 4
    modify = commands[2][0]
    assert "802-11-wireless.hidden" in modify
    assert modify[modify.index("802-11-wireless.hidden") + 1] == "yes"
    assert modify[modify.index("802-11-wireless-security.key-mgmt") + 1] == "wpa-psk"
    assert modify[modify.index("802-11-wireless-security.psk") + 1] == "secret-wifi"
    assert "connection up" in flattened(commands[3][0])


def test_visible_open_profile_has_no_security_block():
    commands = build_wifi_profile_commands("Invites", "", False, "open")
    modify = commands[2][0]
    assert modify[modify.index("802-11-wireless.hidden") + 1] == "no"
    assert "802-11-wireless-security.key-mgmt" not in modify
    assert "802-11-wireless-security.psk" not in modify


def test_wpa3_sae_profile_is_supported():
    commands = build_wifi_profile_commands("WPA3", "secret", True, "sae")
    modify = commands[2][0]
    assert modify[modify.index("802-11-wireless-security.key-mgmt") + 1] == "sae"
