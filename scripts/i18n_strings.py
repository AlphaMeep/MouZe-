"""List every translatable UI string (used to keep mouze/i18n/*.json complete).

    python scripts/i18n_strings.py            # print strings missing from each language
    python scripts/i18n_strings.py --json     # dump all strings as JSON
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def collect() -> list[str]:
    from mouze.builtin.catalog import CATEGORIES
    from mouze.builtin.procedural import STYLES
    from mouze.config import HOTKEY_LABELS
    from mouze.gui.discover_page import SEASON_NAMES
    from mouze.gui.help_page import FAQ, SHORTCUTS
    from mouze.gui.main_window import NAV
    from mouze.gui.profiles_page import EFFECT_CHOICES
    from mouze.gui.widgets import TestArea
    from mouze.overlay.effects import ClickEffect, TrailEffect
    from mouze.roles import ROLE_LABELS

    out: list[str] = []
    for path in sorted((ROOT / "mouze").rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                out.append(node.args[0].value)
    for q, a in FAQ:
        out += [q, a]
    out += [label for label, _ in SHORTCUTS]
    out += [n for n, _ in NAV] + [t for _, t in NAV]
    out += list(SEASON_NAMES.values()) + list(ROLE_LABELS.values()) + list(HOTKEY_LABELS.values())
    out += list(STYLES.values()) + list(TrailEffect.STYLES.values()) + list(ClickEffect.STYLES.values())
    out += [v for _, v in EFFECT_CHOICES] + list(CATEGORIES) + [lbl for _, lbl in TestArea.ZONES]
    out += ["All", "Favorites", "Recent", "Animated", "Imported", "Custom", "Mouse X", "Community"]
    out += ["Classic", "Modern", "Sharp", "Dart", "Dot"]
    out += ["Dark", "Light", "Checker", "Hue", "Saturation", "Brightness", "Opacity", "Animation speed"]
    seen, uniq = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


if __name__ == "__main__":
    strings = collect()
    if "--json" in sys.argv:
        print(json.dumps(strings, indent=1, ensure_ascii=False))
        sys.exit(0)
    from mouze.i18n import LANGUAGES
    for code in LANGUAGES:
        if code == "en":
            continue
        f = ROOT / "mouze" / "i18n" / f"{code}.json"
        table = json.loads(f.read_text("utf-8")) if f.exists() else {}
        missing = [s for s in strings if s not in table]
        extra = [k for k in table if k not in strings]
        bad = [k for k, v in table.items() if sorted(re.findall(r"{\w+}", k)) != sorted(re.findall(r"{\w+}", v))]
        print(f"{code}: {len(strings) - len(missing)}/{len(strings)} translated")
        for label, items in (("missing", missing), ("unused", extra), ("placeholder mismatch", bad)):
            for item in items:
                print(f"   {label}: {item[:90]!r}")
