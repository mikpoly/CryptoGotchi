from pathlib import Path
from jinja2 import Environment


def test_all_templates_parse():
    env = Environment()
    for path in Path("cryptogotchi/templates").glob("*.html"):
        env.parse(path.read_text(encoding="utf-8"))
