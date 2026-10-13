"""Procedural (vector) skins: a *recipe* + a *style* renderer.

A recipe is a small JSON-able dict, e.g.::

    {"pointer": "modern", "style": "neon", "glow": "#00e5ff"}

Recipes are what the built-in library is made of, and what the Designer saves.
"""

from __future__ import annotations

import colorsys
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QTransform

from .. import imaging
from ..qtrender import ensure_qt_app, qimage_to_pil
from ..roles import Role
from ..skin import CursorAnim, Skin, SkinMeta
from . import geometry as geo

STYLES = {
    "solid": "Solid",
    "gradient": "Gradient",
    "neon": "Neon Glow",
    "glass": "Glass",
    "outline": "Outline",
    "pixel": "Retro Pixel",
    "rgb": "RGB Chroma (animated)",
    "flow": "Gradient Flow (animated)",
    "pulse": "Neon Pulse (animated)",
}
ANIMATED_STYLES = {"rgb", "flow", "pulse"}

POINTER_NAMES = {
    "classic": "Classic", "modern": "Modern", "sharp": "Sharp", "dart": "Dart", "dot": "Dot",
    **{f"reticle:{k}": f"Reticle - {v}" for k, v in geo.RETICLE_NAMES.items()},
}

DEFAULT_RECIPE = {
    "pointer": "classic",
    "style": "solid",
    "fill": "#ffffff",
    "outline": "#000000",
    "accent": "#1e88e5",
    "glow": "#00e5ff",
    "gradient": ["#ff512f", "#f09819"],
    "outline_width": 1.5,
    "shadow": False,
    "rainbow": False,
    "frames": 24,
    "frame_delay": 50,
}

ANIM_FRAMES = 24


def qcolor(c: str, alpha: float | None = None) -> QColor:
    r, g, b, a = imaging.parse_hex(c)
    col = QColor(r, g, b, a)
    if alpha is not None:
        col.setAlphaF(max(0.0, min(1.0, alpha * a / 255)))
    return col


def mix(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(round(c1.red() + (c2.red() - c1.red()) * t),
                  round(c1.green() + (c2.green() - c1.green()) * t),
                  round(c1.blue() + (c2.blue() - c1.blue()) * t),
                  round(c1.alpha() + (c2.alpha() - c1.alpha()) * t))


def hue_color(h: float, s=0.95, v=1.0) -> QColor:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return QColor(round(r * 255), round(g * 255), round(b * 255))


class StyleRenderer:
    """Paints a :class:`geo.Shape` with a recipe into a QImage."""

    def __init__(self, recipe: dict):
        self.r = {**DEFAULT_RECIPE, **recipe}
        self.style = self.r["style"]

    # padding (in units) around the 32-unit box so glows are not clipped
    @property
    def pad(self) -> float:
        return {"neon": 2.6, "pulse": 2.6}.get(self.style, 0.0)

    def unit_transform(self, size: int) -> QTransform:
        pad = self.pad
        k = (geo.UNIT - 2 * pad) / geo.UNIT
        s = size / geo.UNIT
        t = QTransform()
        t.scale(s, s)
        t.translate(pad, pad)
        t.scale(k, k)
        return t

    def hotspot(self, shape: geo.Shape, size: int) -> tuple[int, int]:
        p = self.unit_transform(size).map(QPointF(*shape.hotspot))
        return (min(size - 1, max(0, math.floor(p.x()))), min(size - 1, max(0, math.floor(p.y()))))

    # ------------------------------------------------------------------ render
    def render(self, shape: geo.Shape, size: int, phase: float) -> QImage:
        if self.style == "pixel":
            return self._render_pixel(shape, size, phase)
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setTransform(self.unit_transform(size))
        getattr(self, f"_paint_{self.style}", self._paint_solid)(p, shape, phase)
        p.end()
        return img

    def _render_pixel(self, shape, size, phase) -> QImage:
        factor = max(1, round(size / 32))
        base = max(8, size // factor)
        img = QImage(base, base, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setTransform(self.unit_transform(base))
        self._paint_solid(p, shape, phase, width=max(1.0, 32 / base) * 1.05, join=Qt.PenJoinStyle.MiterJoin)
        p.end()
        big = img.scaled(base * factor, base * factor, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.FastTransformation)
        out = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(0)
        q = QPainter(out)
        q.drawImage(0, 0, big)
        q.end()
        return out

    # --------------------------------------------------------------- painters
    def _width(self, shape) -> float:
        w = float(self.r["outline_width"])
        return w * 0.75 if shape.thin else w

    def _join(self):
        return Qt.PenJoinStyle.MiterJoin if self.r["pointer"] == "classic" else Qt.PenJoinStyle.RoundJoin

    def _pen(self, color: QColor, width: float, join=None) -> QPen:
        pen = QPen(color, width)
        pen.setJoinStyle(join or self._join())
        pen.setMiterLimit(3.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        return pen

    def _paint_solid(self, p: QPainter, shape: geo.Shape, phase: float, width=None, join=None, fill_brush=None):
        width = self._width(shape) if width is None else width
        outline = qcolor(self.r["outline"])
        fill = fill_brush or QBrush(qcolor(self.r["fill"]))
        p.setPen(self._pen(outline, width, join))
        p.setBrush(fill)
        p.drawPath(shape.body)
        if shape.lines:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(self._pen(outline, max(0.8, width * 0.6), join))
            for ln in shape.lines:
                p.drawPath(ln)
        if shape.accent is not None:
            p.setPen(self._pen(outline, width * 0.8, join))
            p.setBrush(self._accent_brush(phase))
            p.drawPath(shape.accent)

    def _accent_brush(self, phase: float) -> QBrush:
        if self.style == "rgb" or self.r.get("rainbow"):
            return QBrush(hue_color(phase + 0.5))
        return QBrush(qcolor(self.r["accent"]))

    def _gradient(self, stops: list[str], shift: float = 0.0, repeat=False) -> QLinearGradient:
        g = QLinearGradient(QPointF(2, 2), QPointF(26, 28))
        if repeat:
            g.setSpread(QLinearGradient.Spread.ReflectSpread)
            g.setStart(QPointF(2 - 24 * shift * 2, 2 - 26 * shift * 2))
            g.setFinalStop(QPointF(26 - 24 * shift * 2, 28 - 26 * shift * 2))
        n = max(1, len(stops) - 1)
        for i, c in enumerate(stops):
            g.setColorAt(i / n, qcolor(c))
        return g

    def _paint_gradient(self, p, shape, phase):
        self._paint_solid(p, shape, phase, fill_brush=QBrush(self._gradient(self.r["gradient"])))

    def _paint_flow(self, p, shape, phase):
        stops = list(self.r["gradient"])
        self._paint_solid(p, shape, phase, fill_brush=QBrush(self._gradient(stops, phase, repeat=True)))

    def _paint_rgb(self, p, shape, phase):
        g = QLinearGradient(QPointF(2, 2), QPointF(24, 28))
        for i in range(4):
            g.setColorAt(i / 3, hue_color(phase + i / 4))
        self._paint_solid(p, shape, phase, fill_brush=QBrush(g))

    def _paint_glass(self, p, shape, phase):
        tint = qcolor(self.r["fill"])
        width = self._width(shape)
        # contrast halo so glass stays visible on light backgrounds
        p.setPen(self._pen(QColor(0, 0, 0, 120), width + 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape.body)
        body_fill = QColor(tint)
        body_fill.setAlpha(70)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(body_fill)
        p.drawPath(shape.body)
        hl = QLinearGradient(QPointF(0, 0), QPointF(16, 22))
        hl.setColorAt(0.0, QColor(255, 255, 255, 200))
        hl.setColorAt(0.45, QColor(255, 255, 255, 60))
        hl.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.save()
        p.setClipPath(shape.body)
        p.setBrush(QBrush(hl))
        p.drawRect(QRectF(0, 0, 32, 32))
        p.restore()
        edge = mix(QColor(255, 255, 255, 240), tint, 0.25)
        p.setPen(self._pen(edge, max(0.9, width * 0.8)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape.body)
        for ln in shape.lines:
            p.setPen(self._pen(QColor(255, 255, 255, 200), 0.8))
            p.drawPath(ln)
        if shape.accent is not None:
            acc = qcolor(self.r["accent"])
            acc.setAlpha(210)
            p.setPen(self._pen(QColor(255, 255, 255, 230), 0.9))
            p.setBrush(acc)
            p.drawPath(shape.accent)

    def _glow(self, p, path: QPainterPath, color: QColor, strength: float, fill: QColor | None):
        if fill is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for w, a in ((5.6, 0.07), (4.2, 0.13), (3.0, 0.24), (2.0, 0.42)):
            c = QColor(color)
            c.setAlphaF(min(1.0, a * strength))
            p.setPen(self._pen(c, w, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
        core = mix(color, QColor(255, 255, 255), 0.55)
        p.setPen(self._pen(core, 1.1, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)

    def _neon_color(self, phase: float) -> QColor:
        if self.r.get("rainbow"):
            return hue_color(phase)
        return qcolor(self.r["glow"])

    def _paint_neon(self, p, shape, phase, strength=1.0):
        color = self._neon_color(phase)
        fill = qcolor(self.r.get("neon_fill", "#0a0a12"), 0.55)
        self._glow(p, shape.body, color, strength, fill)
        for ln in shape.lines:
            self._glow(p, ln, color, strength * 0.7, None)
        if shape.accent is not None:
            acc = hue_color(phase + 0.5) if self.r.get("rainbow") else qcolor(self.r["accent"])
            self._glow(p, shape.accent, acc, strength, qcolor("#0a0a12", 0.4))

    def _paint_pulse(self, p, shape, phase):
        strength = 0.55 + 0.75 * (0.5 + 0.5 * math.sin(phase * 2 * math.pi))
        self._paint_neon(p, shape, phase, strength)

    def _paint_outline(self, p, shape, phase):
        color = hue_color(phase) if self.r.get("rainbow") else qcolor(self.r["fill"])
        contrast = qcolor(self.r["outline"])
        w = 1.7 if not shape.thin else 1.4
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(self._pen(contrast, w + 1.6, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(shape.body)
        p.setPen(self._pen(color, w, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(shape.body)
        for ln in shape.lines:
            p.drawPath(ln)
        if shape.accent is not None:
            p.setPen(self._pen(contrast, 1.0))
            p.setBrush(self._accent_brush(phase))
            p.drawPath(shape.accent)


class ProceduralSkin(Skin):
    """A skin drawn from a recipe; renders crisply at any size."""

    def __init__(self, skin_id: str, meta: SkinMeta, recipe: dict, path: Path | None = None):
        super().__init__(skin_id, meta, path)
        self.recipe = {**{k: v for k, v in DEFAULT_RECIPE.items() if k in ("pointer", "style")}, **recipe}
        self.renderer = StyleRenderer(self.recipe)
        self.meta.animated = self.recipe.get("style") in ANIMATED_STYLES or bool(
            self.recipe.get("rainbow"))

    @classmethod
    def from_recipe(cls, skin_id: str, meta: SkinMeta, recipe: dict, path: Path | None = None):
        return cls(skin_id, meta, recipe, path)

    def provided_roles(self) -> set[Role]:
        return set(Role)

    def _render(self, role: Role, size: int) -> CursorAnim:
        ensure_qt_app()
        animated_role = role in (Role.BUSY, Role.WORKING)
        animated = animated_role or self.meta.animated
        n = int(self.recipe.get("frames") or ANIM_FRAMES) if animated else 1
        delay = int(self.recipe.get("frame_delay") or 50)
        pointer = self.recipe.get("pointer", "classic")
        frames = []
        hotspot = (0, 0)
        for i in range(n):
            phase = i / n
            shape = geo.shape_for(role, pointer, phase)
            if i == 0:
                hotspot = self.renderer.hotspot(shape, size)
            img = qimage_to_pil(self.renderer.render(shape, size, phase))
            if self.recipe.get("shadow"):
                s = max(1, round(size / 24))
                img = imaging.add_shadow(img, (s, s + s // 2), blur=max(0.8, size / 36), strength=0.5)
            frames.append(img)
        delays = [delay] * n if n > 1 else [0]
        return CursorAnim(frames, delays, hotspot)
