"""Reusable widgets: animated previews, colour buttons, the cursor test area."""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..qtrender import pil_to_qpixmap
from ..roles import Role
from ..skin import CursorAnim
from . import theme

BACKGROUNDS = {"dark": QColor("#2a2a36"), "light": QColor("#f2f2f5"), "checker": None}


def checker_brush(cell: int = 8) -> QBrush:
    pm = QPixmap(cell * 2, cell * 2)
    pm.fill(QColor("#cfcfd6"))
    p = QPainter(pm)
    p.fillRect(0, 0, cell, cell, QColor("#a9a9b4"))
    p.fillRect(cell, cell, cell, cell, QColor("#a9a9b4"))
    p.end()
    return QBrush(pm)


class AnimClock:
    """One shared timer drives every animated preview (cheap and in sync)."""

    _instance = None

    def __init__(self):
        self.timer = QTimer()
        self.timer.setInterval(33)
        self.listeners: set = set()
        self.timer.timeout.connect(self._tick)
        self.t0 = time.monotonic()

    @classmethod
    def get(cls) -> AnimClock:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add(self, w):
        self.listeners.add(w)
        if not self.timer.isActive():
            self.timer.start()

    def remove(self, w):
        self.listeners.discard(w)
        if not self.listeners:
            self.timer.stop()

    def now_ms(self) -> float:
        return (time.monotonic() - self.t0) * 1000

    def _tick(self):
        for w in list(self.listeners):
            try:
                w.advance()
            except RuntimeError:  # widget deleted
                self.listeners.discard(w)


class AnimatedPreview(QWidget):
    """Draws a CursorAnim scaled to fit, with an optional hotspot marker."""

    def __init__(self, box: int = 64, parent=None, show_hotspot: bool = False, background: str = "dark"):
        super().__init__(parent)
        self.box = box
        self.anim: CursorAnim | None = None
        self.pixmaps: list[QPixmap] = []
        self.index = 0
        self.show_hotspot = show_hotspot
        self.background = background
        self.setFixedSize(box, box)

    def set_anim(self, anim: CursorAnim | None):
        self.anim = anim
        self.pixmaps = [pil_to_qpixmap(f) for f in anim.frames] if anim else []
        self.index = 0
        clock = AnimClock.get()
        if anim is not None and anim.animated:
            clock.add(self)
        else:
            clock.remove(self)
        self.update()

    def set_background(self, bg: str):
        self.background = bg
        self.update()

    def advance(self):
        if self.anim is None or not self.isVisible():
            return
        i = self.anim.frame_index_at(AnimClock.get().now_ms())
        if i != self.index:
            self.index = i
            self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        bg = BACKGROUNDS.get(self.background)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg if bg is not None else checker_brush())
        p.drawRoundedRect(r, 8, 8)
        if self.pixmaps:
            pm = self.pixmaps[min(self.index, len(self.pixmaps) - 1)]
            w = pm.width()
            target = min(self.box - 8, max(w, self.box * 0.6))
            scale = target / w
            ox = (self.box - w * scale) / 2
            oy = (self.box - pm.height() * scale) / 2
            pixel = w <= 32 and scale >= 2
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not pixel)
            p.drawPixmap(QRectF(ox, oy, w * scale, pm.height() * scale), pm, QRectF(pm.rect()))
            if self.show_hotspot and self.anim:
                hx, hy = self.anim.hotspot
                cx, cy = ox + (hx + 0.5) * scale, oy + (hy + 0.5) * scale
                p.setPen(QPen(QColor("#ff3b6b"), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), 3, 3)
        p.end()

    def hideEvent(self, e):  # noqa: N802
        AnimClock.get().remove(self)
        super().hideEvent(e)

    def showEvent(self, e):  # noqa: N802
        if self.anim is not None and self.anim.animated:
            AnimClock.get().add(self)
        super().showEvent(e)


class RoleGrid(QWidget):
    """Every role of a skin, animated, with labels."""

    def __init__(self, box: int = 60, columns: int = 6, parent=None, roles=None):
        super().__init__(parent)
        self.roles = list(roles or Role)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.previews: dict[Role, AnimatedPreview] = {}
        for i, role in enumerate(self.roles):
            cell = QVBoxLayout()
            cell.setSpacing(2)
            prev = AnimatedPreview(box)
            prev.setToolTip(role.label)
            lbl = QLabel(role.label)
            lbl.setProperty("dim", True)
            lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(box + 14)
            lbl.setFixedHeight(28)
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            lbl.setWordWrap(True)
            cell.addWidget(prev, 0, Qt.AlignmentFlag.AlignHCenter)
            cell.addWidget(lbl, 0, Qt.AlignmentFlag.AlignHCenter)
            grid.addLayout(cell, i // columns, i % columns)
            self.previews[role] = prev
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_skin(self, skin, size: int, adj=None):
        for role, prev in self.previews.items():
            prev.set_anim(skin.render(role, size, adj) if skin else None)

    def set_background(self, bg: str):
        for prev in self.previews.values():
            prev.set_background(bg)


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color: str = "#ffffff", parent=None, alpha: bool = False):
        super().__init__(parent)
        self.alpha = alpha
        self.setFixedSize(QSize(44, 26))
        self._color = color
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> str:
        return self._color

    def set_color(self, c: str, emit: bool = False):
        self._color = c
        self._refresh()
        if emit:
            self.colorChanged.emit(c)

    def _refresh(self):
        self.setStyleSheet(f"QPushButton {{ background: {self._color[:7]}; border: 2px solid {theme.BORDER};"
                           f" border-radius: 6px; }} QPushButton:hover {{ border-color: {theme.ACCENT}; }}")
        self.setToolTip(self._color)

    def _pick(self):
        opts = QColorDialog.ColorDialogOption.ShowAlphaChannel if self.alpha else QColorDialog.ColorDialogOption(0)
        c = QColorDialog.getColor(QColor(self._color), self, "Pick a colour", opts)
        if c.isValid():
            name = c.name(QColor.NameFormat.HexArgb if self.alpha else QColor.NameFormat.HexRgb)
            if self.alpha:  # #AARRGGBB -> #RRGGBBAA
                name = "#" + name[3:] + name[1:3]
            self.set_color(name, emit=True)


class LabeledSlider(QWidget):
    valueChanged = Signal(float)

    def __init__(self, minimum: float, maximum: float, value: float, step: float = 1.0,
                 fmt: str = "{:.0f}", parent=None):
        super().__init__(parent)
        self.step = step
        self.fmt = fmt
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(round(minimum / step), round(maximum / step))
        self.slider.setValue(round(value / step))
        self.label = QLabel()
        self.label.setFixedWidth(48)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.label)
        self.slider.valueChanged.connect(self._changed)
        self._update_label()

    def value(self) -> float:
        return self.slider.value() * self.step

    def set_value(self, v: float):
        self.slider.blockSignals(True)
        self.slider.setValue(round(v / self.step))
        self.slider.blockSignals(False)
        self._update_label()

    def _changed(self, _):
        self._update_label()
        self.valueChanged.emit(self.value())

    def _update_label(self):
        self.label.setText(self.fmt.format(self.value()))


class TestArea(QFrame):
    """Hover the zones to try a skin's cursors before applying it."""

    ZONES = [(Role.ARROW, "Normal"), (Role.LINK, "Link"), (Role.TEXT, "Text"), (Role.BUSY, "Busy"),
             (Role.WORKING, "Working"), (Role.PRECISION, "Precision"), (Role.MOVE, "Move"),
             (Role.UNAVAILABLE, "Unavailable"), (Role.HELP, "Help"), (Role.HANDWRITING, "Pen")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.skin = None
        self.size = 32
        self.adj = None
        self._anims: dict[Role, tuple] = {}
        self._hover_role: Role | None = None
        self._frame = -1
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.zones = []
        for i, (role, label) in enumerate(self.ZONES):
            z = QLabel(label)
            z.setAlignment(Qt.AlignmentFlag.AlignCenter)
            z.setMinimumHeight(44)
            z.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            z.setStyleSheet(f"background: {theme.BG_3}; border-radius: 8px; color: {theme.TEXT_DIM};")
            z.setMouseTracking(True)
            z.role = role
            z.installEventFilter(self)
            lay.addWidget(z, i // 5, i % 5)
            self.zones.append(z)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._animate)

    def set_skin(self, skin, size, adj):
        self.skin, self.size, self.adj = skin, size, adj
        self._anims.clear()
        for z in self.zones:
            z.unsetCursor()
            self._apply_zone(z, 0)

    def _cursor_for(self, role, t_ms):
        if self.skin is None:
            return None
        hit = self._anims.get(role)
        if hit is None:
            anim = self.skin.render(role, self.size, self.adj)
            hit = (anim, [pil_to_qpixmap(f) for f in anim.frames])
            self._anims[role] = hit
        anim, pms = hit
        idx = anim.frame_index_at(t_ms)
        hx, hy = anim.hotspot
        return idx, QCursor(pms[idx], hx, hy), anim.animated

    def _apply_zone(self, z, t_ms):
        res = self._cursor_for(z.role, t_ms)
        if res:
            z.setCursor(res[1])

    def eventFilter(self, obj, ev):  # noqa: N802
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.Type.Enter and hasattr(obj, "role"):
            self._hover_role = obj.role
            self._hover_zone = obj
            obj.setStyleSheet(f"background: {theme.BORDER}; border-radius: 8px; color: {theme.TEXT};")
            res = self._cursor_for(obj.role, AnimClock.get().now_ms())
            if res and res[2]:
                self.timer.start()
        elif ev.type() == QEvent.Type.Leave and hasattr(obj, "role"):
            obj.setStyleSheet(f"background: {theme.BG_3}; border-radius: 8px; color: {theme.TEXT_DIM};")
            self._hover_role = None
            self.timer.stop()
        return False

    def _animate(self):
        if self._hover_role is None:
            self.timer.stop()
            return
        res = self._cursor_for(self._hover_role, AnimClock.get().now_ms())
        if res and res[0] != self._frame:
            self._frame = res[0]
            self._hover_zone.setCursor(res[1])
