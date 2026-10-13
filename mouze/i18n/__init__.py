"""Tiny translation layer.

Strings are written in English in the code and wrapped in :func:`tr`.  Each
``<lang>.json`` file in this folder maps the English text to a translation;
anything missing falls back to English.  To add a language, copy ``zh_CN.json``,
translate the values and add it to ``LANGUAGES``.
"""

from __future__ import annotations

import json
import locale
import os
from pathlib import Path

LANGUAGES = {
    "en": "English",
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt_BR": "Português (Brasil)",
    "ru": "Русский",
    "ja": "日本語",
}

_DIR = Path(__file__).parent
_table: dict[str, str] = {}
_lang = "en"


def system_language() -> str:
    code = os.environ.get("MOUZE_LANG") or (locale.getlocale()[0] or "") or os.environ.get("LANG", "")
    code = code.split(".")[0].replace("-", "_")
    if code in LANGUAGES:
        return code
    if code.lower().startswith("zh"):
        return "zh_TW" if code.upper().endswith(("TW", "HK", "MO")) or "Hant" in code else "zh_CN"
    if code.lower().startswith("pt"):
        return "pt_BR"
    short = code[:2].lower()
    return short if short in LANGUAGES else "en"


def set_language(code: str | None) -> str:
    """Load a language ("auto"/None = system language).  Returns the code in use."""
    global _table, _lang
    code = system_language() if not code or code == "auto" else code
    if code not in LANGUAGES:
        code = "en"
    _lang = code
    _table = {}
    path = _DIR / f"{code}.json"
    if code != "en" and path.exists():
        try:
            _table = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            _table = {}
    return code


def current_language() -> str:
    return _lang


def tr(text: str) -> str:
    return _table.get(text, text)
