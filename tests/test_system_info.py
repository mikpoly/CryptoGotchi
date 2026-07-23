from cryptogotchi.system_info import _split_nmcli


def test_split_nmcli_preserves_escaped_colons():
    assert _split_nmcli(r"yes:Maison\:Bureau:87") == ["yes", "Maison:Bureau", "87"]
