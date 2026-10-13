"""The built-in skin library.

Every skin here is an original procedural design (see ``geometry.py``), so the
whole library is MIT licensed along with the code and renders sharp at any
size.  Categories mirror the ones people browse for most: Classic, Color,
Neon, RGB, Gradient, Glass, Retro, Minimal and Crosshair.
"""

from __future__ import annotations

from functools import lru_cache

from ..skin import SkinMeta, slugify
from .geometry import RETICLE_NAMES, RETICLES
from .procedural import ProceduralSkin

AUTHOR = "MouZe"

# (name, fill, outline, accent)
COLOR_PALETTES = [
    ("Crimson", "#e53935", "#2a0505", "#ffffff"),
    ("Tangerine", "#fb8c00", "#2e1600", "#ffffff"),
    ("Sunflower", "#fdd835", "#3a2f00", "#5d4037"),
    ("Lime", "#8bc34a", "#142200", "#ffffff"),
    ("Emerald", "#00a86b", "#002416", "#ffffff"),
    ("Aqua", "#00bcd4", "#002a30", "#ffffff"),
    ("Azure", "#1e88e5", "#001a33", "#ffffff"),
    ("Indigo", "#3f51b5", "#0b0f2b", "#ffd740"),
    ("Violet", "#8e24aa", "#1d0024", "#ffffff"),
    ("Bubblegum", "#f06292", "#33001a", "#ffffff"),
    ("Mint", "#69f0ae", "#00331a", "#004d40"),
    ("Peach", "#ffab91", "#3e1a10", "#bf360c"),
    ("Lavender", "#b39ddb", "#1f1236", "#4a148c"),
    ("Gold", "#ffca28", "#4a3200", "#6d4c00"),
    ("Silver", "#cfd8dc", "#263238", "#1565c0"),
    ("Cocoa", "#795548", "#f5e6dc", "#ffcc80"),
    ("Midnight", "#263238", "#b0bec5", "#4fc3f7"),
    ("Charcoal", "#212121", "#f5f5f5", "#ff5252"),
]

NEON_COLORS = [
    ("Cyan", "#00e5ff"), ("Magenta", "#ff2bd6"), ("Lime", "#76ff03"), ("Red", "#ff1744"),
    ("Orange", "#ff9100"), ("Yellow", "#ffea00"), ("Purple", "#b388ff"), ("Blue", "#2979ff"),
    ("Pink", "#ff80ab"), ("White", "#ffffff"), ("Toxic", "#c6ff00"), ("Ice", "#80d8ff"),
]

GRADIENTS = [
    ("Sunset", ["#ff512f", "#f09819"], "#3a0d00"),
    ("Ocean", ["#2193b0", "#6dd5ed"], "#002233"),
    ("Aurora", ["#00c9ff", "#92fe9d"], "#00303a"),
    ("Vaporwave", ["#ff71ce", "#b967ff", "#01cdfe"], "#1a0030"),
    ("Inferno", ["#f12711", "#f5af19"], "#2a0500"),
    ("Toxic", ["#a8ff78", "#78ffd6"], "#00331d"),
    ("Candy", ["#ff9a9e", "#fecfef"], "#4a0f24"),
    ("Grape", ["#8e2de2", "#4a00e0"], "#f3e5ff"),
    ("Mojito", ["#1d976c", "#93f9b9"], "#00261a"),
    ("Berry", ["#ff512f", "#dd2476"], "#2e0016"),
    ("Steel", ["#e0e6ea", "#5c6f80"], "#121a21"),
    ("Galaxy", ["#302b63", "#6a3093", "#0f0c29"], "#e8e0ff"),
    ("Lemonade", ["#fdfc47", "#24fe41"], "#1b3300"),
    ("Cotton", ["#a1c4fd", "#c2e9fb"], "#0d2647"),
    ("Ember", ["#ff416c", "#ff4b2b"], "#2e000a"),
    ("Lagoon", ["#43cea2", "#185a9d"], "#00182b"),
]

GLASS_TINTS = [
    ("Clear", "#ffffff", "#40c4ff"), ("Frost Blue", "#64b5f6", "#ffffff"),
    ("Rose", "#f48fb1", "#ffffff"), ("Smoke", "#37474f", "#ffffff"),
    ("Mint", "#69f0ae", "#004d40"), ("Amber", "#ffc107", "#4e342e"),
]

RETRO = [
    ("Retro White", "#ffffff", "#000000", "#000080"),
    ("Retro Black", "#000000", "#ffffff", "#c0c0c0"),
    ("Terminal Green", "#33ff33", "#002200", "#003300"),
    ("Amber CRT", "#ffb000", "#2b1a00", "#3b2400"),
    ("Handheld", "#9bbc0f", "#0f380f", "#306230"),
    ("Vapor Pixel", "#ff71ce", "#2d0036", "#01cdfe"),
    ("Retro Blue", "#3b5bdb", "#ffffff", "#ffd43b"),
    ("Retro Red", "#e03131", "#ffffff", "#ffd43b"),
]

MINIMAL = [
    ("White", "#ffffff", "#000000"), ("Black", "#111111", "#ffffff"), ("Cyan", "#00e5ff", "#00262b"),
    ("Pink", "#ff4fa3", "#2b0016"), ("Lime", "#aeea00", "#1c2600"), ("Orange", "#ff9100", "#2b1600"),
]

DOT_COLORS = [
    ("White", "#ffffff", "#000000"), ("Black", "#111111", "#ffffff"), ("Red", "#ff3b30", "#ffffff"),
    ("Cyan", "#00e5ff", "#002a30"), ("Yellow", "#ffeb3b", "#2b2600"), ("Pink", "#ff4fa3", "#ffffff"),
]

CROSSHAIR_COLORS = [
    ("Green", "#00ff66"), ("Cyan", "#00e5ff"), ("Red", "#ff2d2d"), ("Yellow", "#ffee00"),
]

POINTER_LABEL = {"classic": "", "modern": "Modern ", "sharp": "Sharp ", "dart": "Dart "}


def _entries():
    e = []

    def add(name, category, recipe, tags=(), description=""):
        e.append((name, category, list(tags), description, recipe))

    # Classic --------------------------------------------------------------
    for ptr in ("classic", "modern", "sharp", "dart"):
        p = POINTER_LABEL[ptr]
        add(f"{p}Light".strip(), "Classic",
            {"pointer": ptr, "style": "solid", "fill": "#ffffff", "outline": "#000000", "accent": "#1e88e5"},
            ["light", "professional"], "Clean white pointer with a crisp black outline.")
        add(f"{p}Dark".strip(), "Classic",
            {"pointer": ptr, "style": "solid", "fill": "#151518", "outline": "#ffffff", "accent": "#4fc3f7"},
            ["dark", "professional"], "Black pointer with a white outline.")
        add(f"{p}Light Shadow".strip(), "Classic",
            {"pointer": ptr, "style": "solid", "fill": "#ffffff", "outline": "#1a1a1a", "accent": "#1e88e5",
             "shadow": True, "outline_width": 1.2},
            ["light", "professional", "shadow"], "Soft drop shadow for a floating look.")

    # Color ------------------------------------------------------------------
    for cname, fill, outline, accent in COLOR_PALETTES:
        for ptr in ("classic", "modern"):
            p = POINTER_LABEL[ptr]
            add(f"{p}{cname}".strip(), "Color",
                {"pointer": ptr, "style": "solid", "fill": fill, "outline": outline, "accent": accent},
                ["color"], f"Solid {cname.lower()} pointer set.")

    # Neon -------------------------------------------------------------------
    for cname, glow in NEON_COLORS:
        for ptr in ("classic", "dart"):
            p = POINTER_LABEL[ptr]
            accent = "#ffffff" if cname != "White" else "#00e5ff"
            add(f"Neon {p}{cname}".replace("  ", " "), "Neon",
                {"pointer": ptr, "style": "neon", "glow": glow, "accent": accent},
                ["neon", "glow", "dark", "gaming"], f"Glowing {cname.lower()} neon tube outline.")
    for cname, glow in NEON_COLORS[:8]:
        add(f"Pulse {cname}", "Neon",
            {"pointer": "modern", "style": "pulse", "glow": glow, "accent": "#ffffff"},
            ["neon", "animated", "glow", "gaming"], "Neon outline that slowly breathes.")

    # RGB --------------------------------------------------------------------
    for ptr in ("classic", "modern", "sharp", "dart"):
        add(f"RGB Chroma {POINTER_LABEL[ptr] or 'Classic '}".strip(), "RGB",
            {"pointer": ptr, "style": "rgb", "outline": "#0d0d0d"},
            ["rgb", "animated", "gaming", "rainbow"], "Full-spectrum colour cycling, like RGB peripherals.")
    for ptr in ("classic", "sharp", "dart"):
        add(f"RGB Neon {POINTER_LABEL[ptr] or 'Classic '}".strip(), "RGB",
            {"pointer": ptr, "style": "neon", "rainbow": True},
            ["rgb", "neon", "animated", "gaming", "rainbow"], "Neon tube that cycles through every hue.")
    for ptr in ("modern", "dart"):
        add(f"RGB Outline {POINTER_LABEL[ptr].strip()}", "RGB",
            {"pointer": ptr, "style": "outline", "rainbow": True, "outline": "#000000"},
            ["rgb", "animated", "minimal", "rainbow"], "Hollow outline with a rainbow edge.")
    add("RGB Dot", "RGB", {"pointer": "dot", "style": "rgb", "outline": "#0d0d0d"},
        ["rgb", "animated", "dot", "rainbow"], "A colour-cycling dot.")
    add("RGB Reticle", "RGB", {"pointer": "reticle:gap", "style": "rgb", "outline": "#000000",
                               "outline_width": 1.2},
        ["rgb", "animated", "crosshair", "gaming", "rainbow"], "Rainbow gap crosshair.")

    # Gradient ---------------------------------------------------------------
    for gname, stops, outline in GRADIENTS:
        for ptr in ("modern", "classic"):
            p = POINTER_LABEL[ptr]
            name = f"{gname}" if ptr == "modern" else f"{gname} Classic"
            add(name, "Gradient",
                {"pointer": ptr, "style": "gradient", "gradient": stops, "outline": outline,
                 "accent": "#ffffff"},
                ["gradient", "color"], f"{gname} gradient fill.")
    for gname, stops, outline in GRADIENTS[:8]:
        add(f"{gname} Flow", "Gradient",
            {"pointer": "modern", "style": "flow", "gradient": stops, "outline": outline, "accent": "#ffffff"},
            ["gradient", "animated"], f"{gname} gradient that flows across the pointer.")

    # Glass ------------------------------------------------------------------
    for gname, tint, accent in GLASS_TINTS:
        for ptr in ("modern", "classic"):
            name = f"Glass {gname}" + (" Classic" if ptr == "classic" else "")
            add(name, "Glass", {"pointer": ptr, "style": "glass", "fill": tint, "accent": accent},
                ["glass", "transparent", "professional"], "Translucent glass with a bright edge highlight.")

    # Retro ------------------------------------------------------------------
    for rname, fill, outline, accent in RETRO:
        add(rname, "Retro", {"pointer": "classic", "style": "pixel", "fill": fill, "outline": outline,
                             "accent": accent},
            ["retro", "pixel"], "Chunky pixel-art cursor with no anti-aliasing.")

    # Minimal ----------------------------------------------------------------
    for mname, color, contrast in MINIMAL:
        add(f"Outline {mname}", "Minimal",
            {"pointer": "modern", "style": "outline", "fill": color, "outline": contrast, "accent": color},
            ["minimal", "outline"], "Hollow line-art pointer.")
    for dname, color, outline in DOT_COLORS:
        add(f"Dot {dname}", "Minimal",
            {"pointer": "dot", "style": "solid", "fill": color, "outline": outline, "accent": color,
             "outline_width": 1.3},
            ["minimal", "dot"], "A simple dot pointer, hotspot in the centre.")

    # Crosshair --------------------------------------------------------------
    for design in RETICLES:
        for cname, color in CROSSHAIR_COLORS:
            add(f"{RETICLE_NAMES[design]} {cname}", "Crosshair",
                {"pointer": f"reticle:{design}", "style": "solid", "fill": color, "outline": "#000000",
                 "accent": color, "outline_width": 1.1},
                ["crosshair", "gaming", "fps"], "Centre-hotspot crosshair pointer.")
    for design in ("gap", "circle", "scope", "brackets"):
        add(f"Neon {RETICLE_NAMES[design]}", "Crosshair",
            {"pointer": f"reticle:{design}", "style": "neon", "glow": "#ff2bd6", "accent": "#ffffff"},
            ["crosshair", "gaming", "neon"], "Glowing crosshair pointer.")
    return e


CATEGORIES = ["Classic", "Color", "Neon", "RGB", "Gradient", "Glass", "Retro", "Minimal", "Crosshair"]


@lru_cache(maxsize=1)
def builtin_skins() -> tuple[ProceduralSkin, ...]:
    skins = []
    seen = set()
    for name, category, tags, desc, recipe in _entries():
        slug = slugify(f"{category}-{name}")
        assert slug not in seen, slug
        seen.add(slug)
        meta = SkinMeta(name=name, author=AUTHOR, category=category, tags=tags, description=desc,
                        license="MIT")
        skins.append(ProceduralSkin(f"builtin:{slug}", meta, recipe))
    return tuple(skins)
