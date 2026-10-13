"""Regenerate the README gallery image and the app icons.

    python scripts/make_assets.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from mouze.builtin.catalog import CATEGORIES, builtin_skins  # noqa: E402
from mouze.builtin.procedural import ProceduralSkin  # noqa: E402
from mouze.qtrender import ensure_qt_app  # noqa: E402
from mouze.roles import Role  # noqa: E402
from mouze.skin import SkinMeta  # noqa: E402


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def gallery(path: Path, per_row: int = 16, cell: int = 60):
    skins = builtin_skins()
    rows = []
    for cat in CATEGORIES:
        items = [s for s in skins if s.meta.category == cat]
        rows.append((cat, items))
    label_w = 120
    height = sum(((len(items) + per_row - 1) // per_row) * cell for _, items in rows) + 20 * len(rows) + 20
    img = Image.new("RGBA", (label_w + per_row * cell + 20, height), (18, 18, 24, 255))
    d = ImageDraw.Draw(img)
    f = font(15)
    y = 20
    for cat, items in rows:
        d.text((16, y + 18), cat, fill=(232, 232, 240, 255), font=f)
        for i, skin in enumerate(items):
            x = label_w + (i % per_row) * cell
            yy = y + (i // per_row) * cell
            d.rounded_rectangle([x + 2, yy + 2, x + cell - 4, yy + cell - 4], 8, fill=(42, 42, 54, 255))
            a = skin.render(Role.ARROW, 44)
            img.alpha_composite(a.frames[len(a.frames) // 3], (x + 7, yy + 7))
        y += ((len(items) + per_row - 1) // per_row) * cell + 20
    img.save(path)


def icons():
    skin = ProceduralSkin("icon", SkinMeta("icon"), {"pointer": "dart", "style": "gradient",
                                                    "gradient": ["#7c5cff", "#00d1ff"], "outline": "#0b0b14",
                                                    "outline_width": 1.8})
    big = skin.render(Role.ARROW, 256).frames[0]
    big.save(ROOT / "mouze" / "assets" / "icon.png")
    big.save(ROOT / "packaging" / "mouze.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                       (128, 128), (256, 256)])


def effects_demo(path: Path):
    """Simulate pointer paths through the real effect classes and paint them."""
    import math

    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter

    from mouze.overlay.effects import ClickEffect, HaloEffect, LocatorEffect, TrailEffect
    from mouze.qtrender import qimage_to_pil
    from mouze.system.pointer import PointerState

    w, h = 1200, 300
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#121218"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cursor = builtin_skins()[0].render(Role.ARROW, 32)
    from mouze.qtrender import pil_to_qpixmap
    pix = pil_to_qpixmap(cursor.frames[0])
    demos = [
        ("ribbon", TrailEffect({"style": "ribbon", "rainbow": True, "length": 40, "width": 8})),
        ("sparkle", TrailEffect({"style": "sparkle", "color": "#ffd54f", "rainbow": False, "length": 30, "width": 6})),
        ("comet", TrailEffect({"style": "comet", "color": "#00e5ff", "rainbow": False, "length": 30, "width": 10})),
    ]
    for k, (_name, eff) in enumerate(demos):
        x0 = 40 + k * 300
        prev = None
        for i in range(60):
            t = i / 59
            x = x0 + 220 * t
            y = 150 + 70 * math.sin(t * 2 * math.pi)
            st = PointerState(round(x), round(y))
            eff.update(i * 0.008, st, prev)
            prev = st
        eff.paint(p)
        p.drawPixmap(round(prev.x) - cursor.hotspot[0], round(prev.y) - cursor.hotspot[1], pix)
    # clicks + halo + locator on the right
    clicks = ClickEffect({"style": "ripple", "left": "#00e5ff", "size": 46, "duration": 600})
    st0, st1 = PointerState(1010, 110), PointerState(1010, 110, left=True)
    clicks.update(0.0, st1, st0)
    clicks.update(0.25, st1, st1)
    clicks.paint(p)
    p.drawPixmap(1010 - cursor.hotspot[0], 110 - cursor.hotspot[1], pix)
    halo = HaloEffect({"color": "#ffeb3b", "radius": 34, "opacity": 0.45})
    halo.update(0, PointerState(1090, 210), None)
    halo.paint(p)
    p.drawPixmap(1090 - cursor.hotspot[0], 210 - cursor.hotspot[1], pix)
    loc = LocatorEffect({"color": "#ff4081", "shake": False})
    loc.trigger(0.0)
    loc.update(0.62, PointerState(945, 215), None)
    loc.paint(p)
    p.setPen(QColor("#9a9ab0"))
    for i, label in enumerate(["Ribbon trail (rainbow)", "Sparkles", "Comet", "Ripple · halo · locator"]):
        p.drawText(QRectF(40 + i * 300, 268, 280, 24), label)
    p.end()
    qimage_to_pil(img).convert("RGB").save(path, optimize=True)


if __name__ == "__main__":
    ensure_qt_app()
    gallery(ROOT / "docs" / "images" / "gallery.png")
    effects_demo(ROOT / "docs" / "images" / "effects-demo.png")
    icons()
    print("done")
