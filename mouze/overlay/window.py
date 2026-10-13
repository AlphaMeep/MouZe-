"""Transparent, click-through overlay windows (one per screen) that draw effects
and, optionally, the cursor itself."""

from __future__ import annotations

import math
import sys
import time

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ..qtrender import pil_to_qpixmap
from ..roles import Role
from ..system.pointer import PointerState, make_pointer_source
from .effects import ClickEffect, HaloEffect, LocatorEffect, SpotlightEffect, TrailEffect


class OverlayWindow(QWidget):
    def __init__(self, manager: OverlayManager, screen):
        super().__init__(None)
        self.manager = manager
        self.screen_ref = screen
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        if sys.platform.startswith("linux"):
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowTitle("MouZe overlay")
        self.setGeometry(screen.geometry())

    def showEvent(self, event):  # noqa: N802 - Qt API
        super().showEvent(event)
        if sys.platform == "win32":  # pragma: no cover - Windows only
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex |= 0x00000020 | 0x00080000 | 0x08000000 | 0x00000080  # TRANSPARENT|LAYERED|NOACTIVATE|TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)

    def global_rect(self) -> QRect:
        return self.geometry()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(event.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        g = self.geometry()
        p.translate(-g.x(), -g.y())
        self.manager.paint_all(p, QRectF(g))
        p.end()


class OverlayManager(QObject):
    """Owns the effects, polls the pointer and repaints only dirty regions."""

    def __init__(self, cfg: dict, backend=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.backend = backend
        self.pointer = make_pointer_source()
        self.windows: list[OverlayWindow] = []
        self.trail = TrailEffect(cfg["trail"], cursor_provider=self._ghost_cursor)
        self.clicks = ClickEffect(cfg["clicks"])
        self.halo = HaloEffect(cfg["halo"])
        self.spotlight = SpotlightEffect(cfg["spotlight"])
        self.locator = LocatorEffect(cfg["locator"])
        self.prev: PointerState | None = None
        self.paused = False
        self.running = False
        self._dirty_prev: QRectF | None = None
        self._spot_prev = None
        # overlay cursor (draws the skin instead of the OS)
        self.cursor_skin = None
        self.cursor_size = 32
        self.cursor_adj = None
        self._cursor_cache: dict = {}
        self._cursor_t0 = time.monotonic()
        self._cursor_rect = None
        self._tilt = 0.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda *_: self._rebuild())
        app.screenRemoved.connect(lambda *_: self._rebuild())

    # lifecycle ----------------------------------------------------------------
    def configure(self, cfg: dict) -> None:
        self.cfg = cfg
        self.trail.configure(cfg["trail"])
        self.clicks.configure(cfg["clicks"])
        self.halo.configure(cfg["halo"])
        self.spotlight.configure(cfg["spotlight"])
        self.locator.configure(cfg["locator"])
        if self.running:
            self.timer.setInterval(max(4, int(1000 / max(15, int(cfg.get("fps", 120))))))
            self._full_update()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._rebuild()
        self.timer.start(max(4, int(1000 / max(15, int(self.cfg.get("fps", 120))))))

    def stop(self) -> None:
        self.running = False
        self.timer.stop()
        for w in self.windows:
            w.hide()
            w.deleteLater()
        self.windows = []

    def close(self) -> None:
        self.stop()
        self.pointer.close()

    def _rebuild(self) -> None:
        for w in self.windows:
            w.hide()
            w.deleteLater()
        self.windows = []
        if not self.running:
            return
        for screen in QGuiApplication.screens():
            w = OverlayWindow(self, screen)
            w.show()
            self.windows.append(w)

    def set_paused(self, paused: bool) -> None:
        if paused == self.paused:
            return
        self.paused = paused
        for w in self.windows:
            w.setVisible(not paused)

    def set_cursor_skin(self, skin, size: int, adj) -> None:
        self.cursor_skin = skin
        self.cursor_size = size
        self.cursor_adj = adj
        self._cursor_cache = {}

    # frame --------------------------------------------------------------------
    def _enabled(self, name: str) -> bool:
        return bool(self.cfg.get(name, {}).get("enabled"))

    def tick(self) -> None:
        if self.paused or not self.windows:
            return
        st = self.pointer.poll()
        now = time.monotonic()
        prev = self.prev
        self.prev = st
        moved = prev is None or (st.x, st.y) != (prev.x, prev.y)
        effects = self._active_effects()
        for e in effects:
            e.update(now, st, prev)
        self.locator.update(now, st, prev)
        if self._enabled("spotlight"):
            self.spotlight.update(now, st, prev)
            if moved or self._spot_prev is None:
                self._spot_prev = (st.x, st.y)
                self._full_update()
            return
        if self._spot_prev is not None:
            self._spot_prev = None
            self._full_update()
            return
        cursor_active = self.cursor_skin is not None and self.cfg.get("overlay_cursor")
        if not (moved or any(e.busy for e in effects) or self.locator.busy or cursor_active):
            return
        self._update_dirty(st)

    def _active_effects(self):
        out = []
        if self._enabled("trail"):
            out.append(self.trail)
        if self._enabled("clicks"):
            out.append(self.clicks)
        if self._enabled("halo"):
            out.append(self.halo)
        return out

    def _update_dirty(self, st: PointerState):
        rect = QRectF(st.x - 140, st.y - 140, 280, 280)
        for e in self._active_effects() + [self.locator]:
            b = e.bounds()
            if b is not None:
                rect = rect.united(b)
        if self._cursor_rect is not None:
            rect = rect.united(self._cursor_rect)
        area = rect if self._dirty_prev is None else rect.united(self._dirty_prev)
        self._dirty_prev = rect
        r = area.toAlignedRect().adjusted(-4, -4, 4, 4)
        for w in self.windows:
            g = w.geometry()
            inter = r.intersected(g)
            if not inter.isEmpty():
                w.update(inter.translated(-g.x(), -g.y()))

    def _full_update(self):
        for w in self.windows:
            w.update()

    def paint_all(self, p: QPainter, area: QRectF) -> None:
        if self._enabled("spotlight"):
            self.spotlight.paint_full(p, area)
        for e in self._active_effects():
            if e is not self.halo:
                e.paint(p)
        if self._enabled("halo"):
            self.halo.paint(p)
        self.locator.paint(p)
        if self.cursor_skin is not None and self.cfg.get("overlay_cursor"):
            self._paint_cursor(p)

    # overlay cursor -----------------------------------------------------------------
    def _role(self) -> Role:
        if self.backend is not None and getattr(self.backend, "supports_role_detection", False):
            return self.backend.current_role() or Role.ARROW
        return Role.ARROW

    def _frames(self, role: Role):
        hit = self._cursor_cache.get(role)
        if hit is None:
            anim = self.cursor_skin.render(role, min(256, self.cursor_size), self.cursor_adj)
            hit = (anim, [pil_to_qpixmap(f) for f in anim.frames])
            self._cursor_cache[role] = hit
        return hit

    def _paint_cursor(self, p: QPainter):
        st = self.prev
        if st is None:
            return
        anim, pixmaps = self._frames(self._role())
        idx = anim.frame_index_at((time.monotonic() - self._cursor_t0) * 1000)
        pix: QPixmap = pixmaps[idx]
        hx, hy = anim.hotspot
        p.save()
        p.translate(st.x, st.y)
        if self.cfg.get("tilt") and self.prev is not None:
            target = 0.0
            if hasattr(self, "_last_x"):
                target = max(-22.0, min(22.0, (st.x - self._last_x) * 1.2))
            self._tilt += (target - self._tilt) * 0.25
            p.rotate(self._tilt)
        self._last_x = st.x
        p.drawPixmap(QPointF(-hx, -hy), pix)
        p.restore()
        r = max(pix.width(), pix.height()) * math.sqrt(2)
        self._cursor_rect = QRectF(st.x - r, st.y - r, 2 * r, 2 * r)

    def _ghost_cursor(self):
        skin = self.cursor_skin
        if skin is None:
            return None
        anim, pixmaps = self._frames(Role.ARROW)
        return pixmaps[0], anim.hotspot
