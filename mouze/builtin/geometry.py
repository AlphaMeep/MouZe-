"""Vector geometry for every cursor role, drawn in a 32x32 unit box.

All shapes are original designs made for MouZe.  Each role function returns a
:class:`Shape`; animated roles (busy/working) take a ``phase`` in ``[0, 1)``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPolygonF, QTransform

from ..roles import Role

UNIT = 32.0


@dataclass
class Shape:
    body: QPainterPath
    hotspot: tuple[float, float]
    lines: list[QPainterPath] = field(default_factory=list)   # detail strokes
    accent: QPainterPath | None = None                        # filled with the accent colour
    thin: bool = False                                        # line-art (reticles)


# ----------------------------------------------------------------------------- helpers

def poly(points) -> QPainterPath:
    p = QPainterPath()
    p.addPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
    p.closeSubpath()
    return p


def rrect(x, y, w, h, r) -> QPainterPath:
    p = QPainterPath()
    p.addRoundedRect(QRectF(x, y, w, h), r, r)
    return p


def circle(cx, cy, r) -> QPainterPath:
    p = QPainterPath()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p


def line(*pts) -> QPainterPath:
    p = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        p.lineTo(QPointF(*pt))
    return p


def stroke(path: QPainterPath, width: float, round_cap: bool = True) -> QPainterPath:
    s = QPainterPathStroker()
    s.setWidth(width)
    s.setCapStyle(Qt.PenCapStyle.RoundCap if round_cap else Qt.PenCapStyle.FlatCap)
    s.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    out = s.createStroke(path)
    out.setFillRule(Qt.FillRule.WindingFill)
    return out.simplified()


def union(*paths: QPainterPath) -> QPainterPath:
    out = QPainterPath()
    out.setFillRule(Qt.FillRule.WindingFill)
    for p in paths:
        out = out.united(p)
    return out.simplified()


def transformed(path: QPainterPath, *, rotate=0.0, scale=1.0, about=(16, 16), move=(0, 0)) -> QPainterPath:
    t = QTransform()
    t.translate(about[0] + move[0], about[1] + move[1])
    t.rotate(rotate)
    t.scale(scale, scale)
    t.translate(-about[0], -about[1])
    return t.map(path)


def map_point(pt, *, rotate=0.0, scale=1.0, about=(16, 16), move=(0, 0)):
    t = QTransform()
    t.translate(about[0] + move[0], about[1] + move[1])
    t.rotate(rotate)
    t.scale(scale, scale)
    t.translate(-about[0], -about[1])
    p = t.map(QPointF(*pt))
    return (p.x(), p.y())


def annulus(cx, cy, r_out, r_in) -> QPainterPath:
    p = QPainterPath()
    p.setFillRule(Qt.FillRule.OddEvenFill)
    p.addEllipse(QPointF(cx, cy), r_out, r_out)
    p.addEllipse(QPointF(cx, cy), r_in, r_in)
    return p


def ring_sector(cx, cy, r_out, r_in, start_deg, sweep_deg) -> QPainterPath:
    outer = QRectF(cx - r_out, cy - r_out, 2 * r_out, 2 * r_out)
    inner = QRectF(cx - r_in, cy - r_in, 2 * r_in, 2 * r_in)
    p = QPainterPath()
    p.arcMoveTo(outer, start_deg)
    p.arcTo(outer, start_deg, sweep_deg)
    p.arcTo(inner, start_deg + sweep_deg, -sweep_deg)
    p.closeSubpath()
    return p


# ------------------------------------------------------------------------ pointers

POINTERS = {
    # name: (polygon, hotspot)
    "classic": ([(3, 2), (3, 24.5), (8.6, 19.2), (12.4, 27.8), (16.2, 26.2), (12.5, 17.8), (20, 17.8)], (3, 2)),
    "modern": ([(4, 3), (4, 25.5), (9.4, 20.6), (12.9, 28.4), (16.7, 26.8), (13.2, 19.2), (20.4, 19.2)], (4, 3)),
    "sharp": ([(3, 2), (3, 26), (9.6, 20.2), (19.6, 19.4)], (3, 2)),
    "dart": ([(3, 2), (12.4, 25.6), (13.4, 13.4), (25.6, 12.4)], (3, 2)),
}
ARROW_POINTERS = tuple(POINTERS)


def arrow(kind: str = "classic", scale: float = 1.0) -> Shape:
    pts, hs = POINTERS.get(kind, POINTERS["classic"])
    body = poly(pts)
    if scale != 1.0:
        body = transformed(body, scale=scale, about=hs)
    return Shape(body, hs)


def dot_pointer() -> Shape:
    return Shape(circle(16, 16, 5.6), (16, 16))


# ------------------------------------------------------------------------- reticles

def _arms(gap: float, length: float, skip=()):
    c = 16
    segs = {
        "n": ((c, c - gap), (c, c - gap - length)),
        "s": ((c, c + gap), (c, c + gap + length)),
        "w": ((c - gap, c), (c - gap - length, c)),
        "e": ((c + gap, c), (c + gap + length, c)),
    }
    return [line(*seg) for k, seg in segs.items() if k not in skip]


def _ret(paths, width=2.0, extra_fill=()) -> Shape:
    parts = [stroke(p, width) for p in paths] + list(extra_fill)
    return Shape(union(*parts), (16, 16), thin=True)


def _reticle_paths(design: str) -> Shape:
    c = 16
    if design == "cross":
        return _ret([line((c, 4), (c, 28)), line((4, c), (28, c))])
    if design == "gap":
        return _ret(_arms(4.5, 8.5), extra_fill=[circle(c, c, 1.5)])
    if design == "dot":
        return Shape(circle(c, c, 3.2), (16, 16), thin=True)
    if design == "circle":
        return _ret([circle(c, c, 8)], extra_fill=[circle(c, c, 1.6)])
    if design == "t":
        return _ret(_arms(4.5, 8.5, skip=("n",)), extra_fill=[circle(c, c, 1.5)])
    if design == "chevron":
        return _ret([line((9, 23), (c, c), (23, 23))], width=2.4)
    if design == "scope":
        lines = [line((c, 2.5), (c, 11.5)), line((c, 20.5), (c, 29.5)),
                 line((2.5, c), (11.5, c)), line((20.5, c), (29.5, c))]
        return _ret([circle(c, c, 11)] + lines, width=1.5, extra_fill=[circle(c, c, 1.3)])
    if design == "brackets":
        d, k = 9.5, 4.5
        corners = [
            line((c - d, c - d + k), (c - d, c - d), (c - d + k, c - d)),
            line((c + d - k, c - d), (c + d, c - d), (c + d, c - d + k)),
            line((c + d, c + d - k), (c + d, c + d), (c + d - k, c + d)),
            line((c - d + k, c + d), (c - d, c + d), (c - d, c + d - k)),
        ]
        return _ret(corners, extra_fill=[circle(c, c, 1.6)])
    if design == "diamond":
        return _ret([poly([(c, c - 8), (c + 8, c), (c, c + 8), (c - 8, c)])], extra_fill=[circle(c, c, 1.5)])
    if design == "triad":
        ticks = []
        for ang in (90, 210, 330):
            a = math.radians(ang)
            ticks.append(line((c + 4 * math.cos(a), c + 4 * math.sin(a)),
                              (c + 11 * math.cos(a), c + 11 * math.sin(a))))
        return _ret(ticks, width=2.2, extra_fill=[circle(c, c, 1.5)])
    if design == "x":
        segs = []
        for ang in (45, 135, 225, 315):
            a = math.radians(ang)
            segs.append(line((c + 4 * math.cos(a), c + 4 * math.sin(a)),
                             (c + 12 * math.cos(a), c + 12 * math.sin(a))))
        return _ret(segs)
    if design == "hex":
        pts = [(c + 9 * math.cos(math.radians(60 * i + 30)), c + 9 * math.sin(math.radians(60 * i + 30)))
               for i in range(6)]
        return _ret([poly(pts)], extra_fill=[circle(c, c, 1.5)])
    if design == "ticks":
        segs = _arms(8.5, 4.5)
        return _ret([circle(c, c, 6.5)] + segs, width=1.8, extra_fill=[circle(c, c, 1.3)])
    if design == "bold":
        return _ret(_arms(2.8, 6), width=3.4)
    raise KeyError(design)


RETICLES = ["cross", "gap", "dot", "circle", "t", "chevron", "scope", "brackets",
            "diamond", "triad", "x", "hex", "ticks", "bold"]

RETICLE_NAMES = {
    "cross": "Plus", "gap": "Gap Cross", "dot": "Dot", "circle": "Circle Dot",
    "t": "T-Cross", "chevron": "Chevron", "scope": "Scope", "brackets": "Brackets",
    "diamond": "Diamond", "triad": "Triad", "x": "X-Cross", "hex": "Hex",
    "ticks": "Ring Ticks", "bold": "Bold Plus",
}


def reticle(design: str) -> Shape:
    return _reticle_paths(design)


# ---------------------------------------------------------------------- other roles

def hand() -> Shape:
    index = rrect(9.2, 2, 4.6, 16, 2.3)
    middle = rrect(13.5, 10.2, 4.3, 7.5, 2.1)
    ring = rrect(17.5, 11.2, 4.1, 6.8, 2.0)
    pinky = rrect(21.2, 12.6, 3.6, 6.4, 1.8)
    palm = rrect(8.2, 14.5, 16.6, 14.5, 4.6)
    thumb = transformed(rrect(2.5, 15.6, 9.0, 4.4, 2.2), rotate=38, about=(9.6, 19.5))
    body = union(index, middle, ring, pinky, palm, thumb)
    lines = [line((13.6, 14.2), (13.6, 18.2)), line((17.6, 14.6), (17.6, 18.4)),
             line((21.3, 15.4), (21.3, 18.6))]
    return Shape(body, (11.5, 2), lines)


def ibeam() -> Shape:
    body = union(rrect(11.2, 3.5, 9.6, 2.6, 1.1), rrect(11.2, 25.9, 9.6, 2.6, 1.1),
                 QPainterPath(rect_path(14.8, 4.5, 2.4, 23)))
    return Shape(body, (16, 16))


def rect_path(x, y, w, h) -> QPainterPath:
    p = QPainterPath()
    p.addRect(QRectF(x, y, w, h))
    return p


def spinner(phase: float, cx=16.0, cy=16.0, r_out=11.0, r_in=7.0) -> tuple[QPainterPath, QPainterPath]:
    ring = annulus(cx, cy, r_out, r_in)
    start = 90 - phase * 360
    arc = ring_sector(cx, cy, r_out - 0.2, r_in + 0.2, start, -110)
    return ring, arc


def busy(phase: float) -> Shape:
    ring, arc = spinner(phase)
    return Shape(ring, (16, 16), accent=arc)


def working(kind: str, phase: float) -> Shape:
    base = arrow(kind if kind in POINTERS else "classic", 0.82)
    ring, arc = spinner(phase, 24.2, 24.2, 6.6, 3.9)
    return Shape(union(base.body, ring), base.hotspot, accent=arc)


def help_select(kind: str) -> Shape:
    base = arrow(kind if kind in POINTERS else "classic", 0.82)
    q = QPainterPath()
    rect = QRectF(21.0, 12.4, 7.0, 7.0)
    q.arcMoveTo(rect, 160)
    q.arcTo(rect, 160, -250)
    q.lineTo(24.5, 22.4)
    mark = union(stroke(q, 2.5), circle(24.5, 26.6, 1.6))
    return Shape(base.body, base.hotspot, accent=mark)


def precision() -> Shape:
    shape = _ret(_arms(3.6, 9.4))
    shape.thin = False
    return shape


def handwriting() -> Shape:
    def pencil_t(path):
        t = QTransform()
        t.translate(4, 28)
        t.rotate(-45)
        return t.map(path)

    tip = poly([(0, 0), (6.5, -3.4), (6.5, 3.4)])
    shaft = rect_path(6.5, -3.4, 15.5, 6.8)
    eraser = rrect(21.0, -3.4, 6.0, 6.8, 1.8)
    body = pencil_t(union(tip, shaft, eraser))
    lines = [pencil_t(line((6.5, -3.4), (6.5, 3.4))), pencil_t(line((21.6, -3.4), (21.6, 3.4)))]
    lead = pencil_t(poly([(0, 0), (2.5, -1.3), (2.5, 1.3)]))
    return Shape(body, (4, 28), lines, accent=lead)


def unavailable() -> Shape:
    ring = annulus(16, 16, 11.5, 7.8)
    bar = transformed(rect_path(16 - 9.0, 16 - 1.85, 18.0, 3.7), rotate=45)
    return Shape(union(ring, bar), (16, 16))


def _double_arrow() -> QPainterPath:
    return poly([(16, 2), (22.8, 9.6), (17.7, 9.6), (17.7, 22.4), (22.8, 22.4), (16, 30),
                 (9.2, 22.4), (14.3, 22.4), (14.3, 9.6), (9.2, 9.6)])


def size_arrow(angle: float) -> Shape:
    scale = 0.9 if angle % 90 else 1.0
    return Shape(transformed(_double_arrow(), rotate=angle, scale=scale), (16, 16))


def move() -> Shape:
    v = poly([(16, 2), (21.2, 7.8), (17.4, 7.8), (17.4, 24.2), (21.2, 24.2), (16, 30),
              (10.8, 24.2), (14.6, 24.2), (14.6, 7.8), (10.8, 7.8)])
    h = transformed(v, rotate=90)
    return Shape(union(v, h), (16, 16))


def alternate() -> Shape:
    return Shape(poly([(16, 2), (25.2, 12.4), (18.5, 12.4), (18.5, 29.5), (13.5, 29.5),
                       (13.5, 12.4), (6.8, 12.4)]), (16, 2))


def pin(kind: str) -> Shape:
    base = arrow(kind if kind in POINTERS else "classic", 0.82)
    drop = QPainterPath()
    drop.setFillRule(Qt.FillRule.OddEvenFill)
    head = union(circle(24.5, 19.5, 4.8), poly([(20.4, 21.8), (28.6, 21.8), (24.5, 29.5)]))
    drop.addPath(head)
    drop.addPath(circle(24.5, 19.5, 1.8))
    return Shape(base.body, base.hotspot, accent=drop)


def person(kind: str) -> Shape:
    base = arrow(kind if kind in POINTERS else "classic", 0.82)
    head = circle(24.5, 17.6, 3.0)
    shoulders = QPainterPath()
    shoulders.moveTo(18.8, 29.6)
    shoulders.cubicTo(18.8, 23.0, 30.2, 23.0, 30.2, 29.6)
    shoulders.closeSubpath()
    return Shape(base.body, base.hotspot, accent=union(head, shoulders))


def shape_for(role: Role, pointer: str, phase: float = 0.0) -> Shape:
    """Return the geometry for ``role`` given the skin's main ``pointer`` design."""
    arrow_kind = pointer if pointer in POINTERS else "classic"
    if role == Role.ARROW:
        if pointer == "dot":
            return dot_pointer()
        if pointer.startswith("reticle:"):
            return reticle(pointer.split(":", 1)[1])
        return arrow(arrow_kind)
    if role == Role.LINK:
        return hand()
    if role == Role.TEXT:
        return ibeam()
    if role == Role.BUSY:
        return busy(phase)
    if role == Role.WORKING:
        return working(arrow_kind, phase)
    if role == Role.HELP:
        return help_select(arrow_kind)
    if role == Role.PRECISION:
        if pointer.startswith("reticle:"):
            return reticle(pointer.split(":", 1)[1])
        return precision()
    if role == Role.HANDWRITING:
        return handwriting()
    if role == Role.UNAVAILABLE:
        return unavailable()
    if role == Role.SIZE_NS:
        return size_arrow(0)
    if role == Role.SIZE_EW:
        return size_arrow(90)
    if role == Role.SIZE_NWSE:
        return size_arrow(-45)
    if role == Role.SIZE_NESW:
        return size_arrow(45)
    if role == Role.MOVE:
        return move()
    if role == Role.ALTERNATE:
        return alternate()
    if role == Role.PIN:
        return pin(arrow_kind)
    if role == Role.PERSON:
        return person(arrow_kind)
    raise KeyError(role)
