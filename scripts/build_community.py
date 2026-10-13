"""Build the starter community catalog in ``community/``.

    python scripts/build_community.py

Anyone can host a catalog the same way: a folder with ``index.json``, the
skin files and preview images, served from GitHub or any web server.  To add
your own skin to this catalog, put the ``.mouzeskin`` file in
``community/skins/`` and a preview in ``community/previews/``, add an entry
to ``EXTERNAL`` below (or edit ``index.json`` by hand) and open a pull request.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mouze.builtin.procedural import ProceduralSkin  # noqa: E402
from mouze.formats.packs import export_preview_png  # noqa: E402
from mouze.qtrender import ensure_qt_app  # noqa: E402
from mouze.skin import SkinMeta, save_skin  # noqa: E402

AUTHOR = "MouZe community"

STARTER = [
    ("sakura-glass", "Sakura Glass", "Glass", ["pink", "glass", "cute"],
     {"pointer": "modern", "style": "glass", "fill": "#ffc1e3", "accent": "#ff4f9a"},
     "Cherry-blossom pink glass."),
    ("lava-lamp", "Lava Lamp", "Gradient", ["animated", "retro", "warm"],
     {"pointer": "classic", "style": "flow", "gradient": ["#ff3d00", "#ffab00", "#d500f9"], "outline": "#1a0010",
      "accent": "#ffffff"}, "Slowly flowing lava colours."),
    ("deep-sea", "Deep Sea", "Neon", ["blue", "neon", "animated"],
     {"pointer": "dart", "style": "pulse", "glow": "#00b8d4", "accent": "#64ffda"},
     "Bioluminescent glow from the deep."),
    ("cyber-lime", "Cyber Lime", "Neon", ["green", "neon", "gaming"],
     {"pointer": "sharp", "style": "neon", "glow": "#c6ff00", "accent": "#00e5ff"}, "Hard-edged cyberpunk lime."),
    ("midnight-pumpkin", "Midnight Pumpkin", "Seasonal", ["halloween", "seasonal", "animated"],
     {"pointer": "dart", "style": "pulse", "glow": "#ff6d00", "accent": "#b388ff"},
     "A pumpkin glow for spooky season."),
    ("arctic-pixel", "Arctic Pixel", "Retro", ["pixel", "retro", "winter"],
     {"pointer": "classic", "style": "pixel", "fill": "#e1f5fe", "outline": "#01579b", "accent": "#4fc3f7"},
     "Chunky icy pixel art."),
    ("aurora-borealis", "Aurora Borealis", "Gradient", ["animated", "green", "winter"],
     {"pointer": "modern", "style": "flow", "gradient": ["#00ffa3", "#00b4d8", "#7b2ff7"], "outline": "#001018",
      "accent": "#ffffff"}, "Northern lights rippling across the pointer."),
    ("monochrome-sniper", "Monochrome Sniper", "Crosshair", ["crosshair", "gaming", "minimal"],
     {"pointer": "reticle:scope", "style": "solid", "fill": "#ffffff", "outline": "#000000", "accent": "#ffffff",
      "outline_width": 1.0}, "A crisp black-and-white scope for any background."),
]

# Skins contributed as ready-made files: (id, name, author, category, tags, description, animated, version)
EXTERNAL: list[tuple] = []


def main():
    ensure_qt_app()
    out = ROOT / "community"
    (out / "skins").mkdir(parents=True, exist_ok=True)
    (out / "previews").mkdir(parents=True, exist_ok=True)
    entries = []
    today = dt.date.today().isoformat()
    for sid, name, category, tags, recipe, desc in STARTER:
        meta = SkinMeta(name=name, author=AUTHOR, category=category, tags=tags, description=desc, license="MIT")
        skin = ProceduralSkin(f"community:{sid}", meta, recipe)
        save_skin(skin, out / "skins" / f"{sid}.mouzeskin", size=64)
        export_preview_png(skin, out / "previews" / f"{sid}.png", 40)
        entries.append({"id": sid, "name": name, "author": AUTHOR, "description": desc, "category": category,
                        "tags": tags, "version": "1.0", "updated": today, "animated": skin.animated,
                        "url": f"skins/{sid}.mouzeskin", "preview": f"previews/{sid}.png", "license": "MIT"})
    for sid, name, author, category, tags, desc, animated, version in EXTERNAL:
        entries.append({"id": sid, "name": name, "author": author, "description": desc, "category": category,
                        "tags": tags, "version": version, "animated": animated,
                        "url": f"skins/{sid}.mouzeskin", "preview": f"previews/{sid}.png"})
    index = {"name": "MouZe Community", "description": "Skins shared by the MouZe community. MIT unless noted.",
             "skins": entries}
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n", "utf-8")
    print(f"wrote {len(entries)} entries to {out}")


if __name__ == "__main__":
    main()
