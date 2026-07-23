import re
from pathlib import Path

from cryptogotchi.i18n import TRANSLATIONS


def test_all_template_and_route_translation_keys_exist_in_en_and_fr():
    keys: set[str] = set()
    for path in Path("cryptogotchi/templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        keys.update(re.findall(r"(?<![A-Za-z0-9_])t\(['\"]([^'\"]+)", text))

    app_text = Path("cryptogotchi/app.py").read_text(encoding="utf-8")
    keys.update(re.findall(r"(?<![A-Za-z0-9_])tr\(['\"]([^'\"]+)", app_text))
    keys.update(re.findall(r"(?<![A-Za-z0-9_])translate\(['\"]([^'\"]+)", app_text))

    for language in ("en", "fr"):
        missing = sorted(key for key in keys if key not in TRANSLATIONS[language])
        assert missing == [], f"Missing {language} translations: {missing}"
