"""Cursor effects drawn on the transparent overlay.

All coordinates are global (virtual desktop) logical pixels.  Each effect
reports the area it needs repainted so the overlay only redraws small regions.
"""

from __future__ import annotations

import math
import random
import time
from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

from ..imaging import parse_hex
from ..system.pointer import PointerState


def color(c: str, alpha: float = 1.0) -> QColor:
    r, g, b, a = parse_hex(c)
    q = QColor(r, g, b)
    q.setAlphaF(max(0.0, min(1.0, alpha * a / 255)))
    return q


def hue(h: float, alpha: float = 1.0, s: float = 0.9, v: float = 1.0) -> QColor:
    q = QColor.fromHsvF(h % 1.0, s, v)
    q.setAlphaF(max(0.0, min(1.0, alpha)))
    return q


def _rect_around(x: float, y: float, r: float) -> QRectF:
    return QRectF(x - r, y - r, 2 * r, 2 * r)


class Effect:
    name = "effect"

    def __init__(self, cfg: dict):
        self.cfg = dict(cfg)

    def configure(self, cfg: dict) -> None:
        self.cfg = dict(cfg)

    def update(self, now: float, st: PointerState, prev: PointerState | None) -> None:
        pass

    def paint(self, p: QPainter) -> None:
        pass

    def bounds(self) -> QRectF | None:
        """Area (global coords) touched by the last paint; None if nothing visible."""
        return None

    @property
    def busy(self) -> bool:
        """True while the effect is animating even if the pointer is still."""
        return False


# ============================================================================ trails

@dataclass
class _Pt:
    x: float
    y: float
    t: float


@dataclass
class _Particle:
    x: float
    y: float
    vx: float
    vy: float
    born: float
    life: float
    size: float
    hue: float
    kind: str = "star"
    spin: float = 0.0


class TrailEffect(Effect):
    name = "trail"
    STYLES = {"ribbon": "Ribbon", "comet": "Comet dots", "sparkle": "Sparkles",
              "bubbles": "Bubbles", "ghost": "Ghost cursors"}

    def __init__(self, cfg, cursor_provider=None):
        super().__init__(cfg)
        self.points: deque[_Pt] = deque()
        self.particles: list[_Particle] = []
        self.cursor_provider = cursor_provider  # () -> (QPixmap, hotspot) for ghost style
        self._bounds: QRectF | None = None
        self._last_spawn = 0.0

    @property
    def style(self) -> str:
        return self.cfg.get("style", "ribbon")

    @property
    def busy(self) -> bool:
        return bool(self.points) or bool(self.particles)

    def _color(self, i: float, alpha: float, now: float) -> QColor:
        if self.cfg.get("rainbow"):
            return hue(now * 0.25 + i * 0.6, alpha)
        return color(self.cfg.get("color", "#00e5ff"), alpha)

    def update(self, now, st, prev):
        length = max(2, int(self.cfg.get("length", 18)))
        lifetime = 0.018 * length + 0.12
        moved = prev is None or (st.x, st.y) != (prev.x, prev.y)
        if self.style in ("sparkle", "bubbles"):
            if moved and prev is not None and now - self._last_spawn > 0.012:
                self._last_spawn = now
                dist = math.hypot(st.x - prev.x, st.y - prev.y)
                n = min(6, 1 + int(dist / 14))
                for _ in range(n):
                    a = random.uniform(0, 2 * math.pi)
                    sp = random.uniform(10, 60)
                    w = float(self.cfg.get("width", 6))
                    if self.style == "bubbles":
                        self.particles.append(_Particle(st.x + random.uniform(-4, 4), st.y + random.uniform(-4, 4),
                                                        random.uniform(-15, 15), random.uniform(-70, -30), now,
                                                        lifetime * 2.2, random.uniform(w * 0.6, w * 1.6),
                                                        random.random(), "bubble"))
                    else:
                        self.particles.append(_Particle(st.x, st.y, math.cos(a) * sp, math.sin(a) * sp + 20,
                                                        now, lifetime * 1.6, random.uniform(w * 0.5, w * 1.2),
                                                        random.random(), "star", random.uniform(-6, 6)))
            self.particles = [pt for pt in self.particles if now - pt.born < pt.life][-400:]
        else:
            if moved:
                self.points.append(_Pt(st.x, st.y, now))
            while self.points and (now - self.points[0].t > lifetime or len(self.points) > length * 3):
                self.points.popleft()
            if self.points and not moved and now - self.points[-1].t > lifetime:
                self.points.clear()
        self._now = now

    def paint(self, p):
        now = getattr(self, "_now", time.monotonic())
        width = float(self.cfg.get("width", 6))
        xs, ys = [], []
        if self.style in ("sparkle", "bubbles"):
            for pt in self.particles:
                age = (now - pt.born) / pt.life
                if age >= 1:
                    continue
                dt = now - pt.born
                x = pt.x + pt.vx * dt
                y = pt.y + pt.vy * dt + (25 * dt * dt if pt.kind == "star" else 0)
                alpha = (1 - age) ** 1.4
                c = hue(pt.hue, alpha) if self.cfg.get("rainbow") else color(self.cfg.get("color", "#00e5ff"), alpha)
                s = pt.size * (1 - 0.5 * age)
                if pt.kind == "bubble":
                    p.setBrush(QColor(c.red(), c.green(), c.blue(), int(40 * alpha)))
                    p.setPen(QPen(c, 1.4))
                    p.drawEllipse(QPointF(x, y), s, s)
                else:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(c)
                    p.drawPath(_star(x, y, s, s * 0.42, pt.spin * dt))
                xs += [x - s - 2, x + s + 2]
                ys += [y - s - 2, y + s + 2]
        elif self.points:
            pts = list(self.points)
            n = len(pts)
            if self.style == "ribbon" and n >= 2:
                p.setBrush(Qt.BrushStyle.NoBrush)
                for i in range(1, n):
                    f = i / (n - 1)
                    pen = QPen(self._color(f, f * 0.9, now), max(0.6, width * f))
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    p.setPen(pen)
                    p.drawLine(QPointF(pts[i - 1].x, pts[i - 1].y), QPointF(pts[i].x, pts[i].y))
            elif self.style == "comet":
                p.setPen(Qt.PenStyle.NoPen)
                for i, pt in enumerate(pts):
                    f = (i + 1) / n
                    p.setBrush(self._color(f, f * 0.85, now))
                    p.drawEllipse(QPointF(pt.x, pt.y), width * 0.5 * f + 0.8, width * 0.5 * f + 0.8)
            elif self.style == "ghost" and self.cursor_provider:
                prov = self.cursor_provider()
                if prov:
                    pix, (hx, hy) = prov
                    step = max(1, n // 6)
                    for i in range(0, n - 1, step):
                        f = (i + 1) / n
                        p.setOpacity(f * 0.45)
                        p.drawPixmap(QPointF(pts[i].x - hx, pts[i].y - hy), pix)
                    p.setOpacity(1.0)
                    xs += [pt.x - hx for pt in pts] + [pt.x - hx + pix.width() for pt in pts]
                    ys += [pt.y - hy for pt in pts] + [pt.y - hy + pix.height() for pt in pts]
            xs += [pt.x - width for pt in pts] + [pt.x + width for pt in pts]
            ys += [pt.y - width for pt in pts] + [pt.y + width for pt in pts]
        self._bounds = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).adjusted(-3, -3, 3, 3) \
            if xs else None

    def bounds(self):
        return self._bounds


def _star(cx, cy, r_out, r_in, rot) -> QPainterPath:
    path = QPainterPath()
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = rot + i * math.pi / 5 - math.pi / 2
        pt = QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path


# ============================================================================ clicks

@dataclass
class _Click:
    x: float
    y: float
    t: float
    color: QColor
    seed: int


class ClickEffect(Effect):
    name = "clicks"
    STYLES = {"ripple": "Ripple", "burst": "Burst", "confetti": "Confetti", "pulse": "Solid pulse"}

    def __init__(self, cfg):
        super().__init__(cfg)
        self.clicks: list[_Click] = []
        self._bounds = None

    @property
    def busy(self):
        return bool(self.clicks)

    def update(self, now, st, prev):
        if prev is not None:
            for btn in ("left", "right", "middle"):
                if getattr(st, btn) and not getattr(prev, btn):
                    self.clicks.append(_Click(st.x, st.y, now, color(self.cfg.get(btn, "#00e5ff")),
                                              random.randrange(1 << 30)))
        dur = max(0.1, float(self.cfg.get("duration", 450)) / 1000)
        self.clicks = [c for c in self.clicks if now - c.t < dur]
        self._now = now

    def paint(self, p):
        now = getattr(self, "_now", time.monotonic())
        dur = max(0.1, float(self.cfg.get("duration", 450)) / 1000)
        size = float(self.cfg.get("size", 38))
        style = self.cfg.get("style", "ripple")
        rect = None
        for c in self.clicks:
            f = min(1.0, (now - c.t) / dur)
            ease = 1 - (1 - f) ** 3
            alpha = 1 - f
            col = QColor(c.color)
            col.setAlphaF(alpha * col.alphaF())
            if style == "ripple":
                p.setBrush(Qt.BrushStyle.NoBrush)
                for k, delay in enumerate((0.0, 0.18)):
                    g = max(0.0, (f - delay) / (1 - delay))
                    if g <= 0:
                        continue
                    r = size * (1 - (1 - g) ** 3)
                    cc = QColor(col)
                    cc.setAlphaF(max(0.0, (1 - g)) * c.color.alphaF())
                    p.setPen(QPen(cc, 3.0 - k))
                    p.drawEllipse(QPointF(c.x, c.y), r, r)
            elif style == "pulse":
                grad = QRadialGradient(QPointF(c.x, c.y), size * ease + 1)
                cc = QColor(col)
                grad.setColorAt(0, cc)
                cc2 = QColor(col)
                cc2.setAlpha(0)
                grad.setColorAt(1, cc2)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(grad))
                p.drawEllipse(QPointF(c.x, c.y), size * ease + 1, size * ease + 1)
            elif style == "burst":
                pen = QPen(col, 2.5)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                for i in range(10):
                    a = i * math.pi / 5 + (c.seed % 100) / 100
                    r0 = size * 0.25 + size * 0.55 * ease
                    r1 = r0 + size * 0.28 * (1 - f)
                    p.drawLine(QPointF(c.x + r0 * math.cos(a), c.y + r0 * math.sin(a)),
                               QPointF(c.x + r1 * math.cos(a), c.y + r1 * math.sin(a)))
            else:  # confetti
                rnd = random.Random(c.seed)
                p.setPen(Qt.PenStyle.NoPen)
                for _ in range(18):
                    a = rnd.uniform(0, 2 * math.pi)
                    dist = size * rnd.uniform(0.4, 1.0) * ease
                    x = c.x + dist * math.cos(a)
                    y = c.y + dist * math.sin(a) + size * 0.5 * f * f
                    cc = hue(rnd.random(), alpha)
                    p.save()
                    p.translate(x, y)
                    p.rotate(rnd.uniform(0, 360) + f * 360)
                    p.setBrush(cc)
                    p.drawRect(QRectF(-3, -1.5, 6, 3))
                    p.restore()
            r = _rect_around(c.x, c.y, size * 1.6 + 6)
            rect = r if rect is None else rect.united(r)
        self._bounds = rect

    def bounds(self):
        return self._bounds


# ============================================================================ halo

class HaloEffect(Effect):
    name = "halo"

    def update(self, now, st, prev):
        self._pos = (st.x, st.y)

    def paint(self, p):
        x, y = getattr(self, "_pos", (0, 0))
        r = float(self.cfg.get("radius", 30))
        op = float(self.cfg.get("opacity", 0.35))
        grad = QRadialGradient(QPointF(x, y), r)
        c = color(self.cfg.get("color", "#ffeb3b"), op)
        grad.setColorAt(0.0, c)
        grad.setColorAt(0.75, color(self.cfg.get("color", "#ffeb3b"), op * 0.8))
        grad.setColorAt(1.0, color(self.cfg.get("color", "#ffeb3b"), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(x, y), r, r)
        self._bounds = _rect_around(x, y, r + 2)

    def bounds(self):
        return getattr(self, "_bounds", None)


# ============================================================================ spotlight

class SpotlightEffect(Effect):
    """Dims everything except a circle around the pointer (presentations)."""

    name = "spotlight"
    full_screen = True

    def update(self, now, st, prev):
        self._pos = (st.x, st.y)

    def paint_full(self, p: QPainter, area: QRectF):
        x, y = getattr(self, "_pos", (0, 0))
        r = float(self.cfg.get("radius", 160))
        dim = float(self.cfg.get("dim", 0.6))
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(area)
        path.addEllipse(QPointF(x, y), r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(255 * dim)))
        p.drawPath(path)
        grad = QRadialGradient(QPointF(x, y), r)
        grad.setColorAt(0.85, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, int(255 * dim * 0.6)))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(x, y), r, r)


# ============================================================================ locator

class LocatorEffect(Effect):
    """Radar ping around the pointer - on hotkey, or when the mouse is shaken."""

    name = "locator"
    DURATION = 0.9

    def __init__(self, cfg):
        super().__init__(cfg)
        self.started = None
        self._moves: deque[tuple[float, int]] = deque()
        self._last_trigger = 0.0
        self._bounds = None

    @property
    def busy(self):
        return self.started is not None

    def trigger(self, now=None):
        self.started = now if now is not None else time.monotonic()
        self._last_trigger = self.started

    def update(self, now, st, prev):
        self._pos = (st.x, st.y)
        if prev is not None and self.cfg.get("shake", True):
            dx = st.x - prev.x
            if abs(dx) > 6:
                self._moves.append((now, 1 if dx > 0 else -1))
            while self._moves and now - self._moves[0][0] > 0.55:
                self._moves.popleft()
            flips = sum(1 for a, b in zip(self._moves, list(self._moves)[1:]) if a[1] != b[1])
            need = max(2, 9 - int(self.cfg.get("sensitivity", 5)))
            if flips >= need and now - self._last_trigger > 1.5:
                self._moves.clear()
                self.trigger(now)
        if self.started is not None and now - self.started > self.DURATION:
            self.started = None
        self._now = now

    def paint(self, p):
        if self.started is None:
            self._bounds = None
            return
        now = getattr(self, "_now", time.monotonic())
        x, y = getattr(self, "_pos", (0, 0))
        f = min(1.0, (now - self.started) / self.DURATION)
        base = color(self.cfg.get("color", "#ff4081"))
        p.setBrush(Qt.BrushStyle.NoBrush)
        max_r = 110
        for k in range(3):
            g = (f + k / 3) % 1.0
            r = max_r * (1 - g) + 10
            c = QColor(base)
            c.setAlphaF((1 - f) * (0.35 + 0.65 * g))
            p.setPen(QPen(c, 4))
            p.drawEllipse(QPointF(x, y), r, r)
        self._bounds = _rect_around(x, y, max_r + 16)

    def bounds(self):
        return self._bounds
