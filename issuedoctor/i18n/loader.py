import json
from pathlib import Path
from typing import Any

from flask import Flask


def load_catalog(locale: str = "zh_CN") -> dict[str, str]:
    path = Path(__file__).with_name(f"{locale}.json")
    with path.open(encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def register_i18n(app: Flask) -> None:
    catalog = load_catalog()

    def translate(key: str, **values: Any) -> str:
        text = catalog.get(key, key)
        return text.format(**values) if values else text

    app.jinja_env.globals["t"] = translate
    app.extensions["issuedoctor_i18n"] = catalog

