from cryptogotchi.i18n import normalize_language, translate


def test_english_is_default_and_french_is_available():
    assert normalize_language(None) == "en"
    assert translate("nav.market") == "Market"
    assert translate("nav.market", "fr") == "Marché"
    assert translate("flash.coin_added", "en", coin="SOL") == "SOL added. Its 24-hour chart is being prepared."
