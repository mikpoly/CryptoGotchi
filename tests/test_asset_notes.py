from cryptogotchi.config import asset_data_note, canonical_data_note_key, default_config


def test_spcx_never_inherits_gold_note():
    spcx = {
        "id": "spacex-robinhood-token",
        "symbol": "SPCX",
        "name": "SpaceX Robinhood Token",
        "source": "coingecko",
        "asset_kind": "tokenized_asset",
        "data_note": "Spot gold per troy ounce from Gold API; intraday history is built locally.",
    }
    assert canonical_data_note_key(spcx) == "tokenized_asset"
    note = asset_data_note(spcx, "en")
    assert "Tokenized asset" in note
    assert "gold" not in note.lower()


def test_xau_note_is_localized_and_asset_specific():
    xau = {"id": "spot-xau", "symbol": "XAU", "source": "gold_api", "asset_kind": "commodity"}
    assert canonical_data_note_key(xau) == "spot_metal"
    assert "troy ounce" in asset_data_note(xau, "en")
    assert "once troy" in asset_data_note(xau, "fr")


def test_default_revision_is_v070():
    assert default_config()["main"]["config_revision"] == 12
