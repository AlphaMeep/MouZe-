"""Global pointer position and button state, polled (no input hooks).

Positions always come from Qt's ``QCursor.pos()`` so they are in the same
DPI-independent coordinates as our windows.  Buttons come from
``GetAsyncKeyState`` on Windows and, elsewhere, from the optional ``pynput``
package if it is installed.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass


@dataclass
class PointerState:
    x: int
    y: int
    left: bool = False
    right: bool = False
    middle: bool = False


class PointerSource:
    def poll(self) -> PointerState:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:
        pass


class WindowsPointer(PointerSource):  # pragma: no cover - Windows only
    def __init__(self):
        import ctypes
        self._user32 = ctypes.windll.user32
        # Respect swapped buttons for left-handed users.
        self._swap = bool(self._user32.GetSystemMetrics(23))  # SM_SWAPBUTTON

    def poll(self) -> PointerState:
        from PySide6.QtGui import QCursor
        u = self._user32
        pos = QCursor.pos()
        lb = bool(u.GetAsyncKeyState(0x01) & 0x8000)
        rb = bool(u.GetAsyncKeyState(0x02) & 0x8000)
        mb = bool(u.GetAsyncKeyState(0x04) & 0x8000)
        if self._swap:
            lb, rb = rb, lb
        return PointerState(pos.x(), pos.y(), lb, rb, mb)


class QtPointer(PointerSource):
    def __init__(self):
        self._buttons = {"left": False, "right": False, "middle": False}
        self._listener = None
        self._lock = threading.Lock()
        try:
            from pynput import mouse  # optional dependency

            def on_click(_x, _y, button, pressed):
                name = getattr(button, "name", "")
                if name in self._buttons:
                    with self._lock:
                        self._buttons[name] = pressed

            self._listener = mouse.Listener(on_click=on_click)
            self._listener.daemon = True
            self._listener.start()
        except Exception:  # noqa: BLE001 - pynput missing or no display access
            self._listener = None

    @property
    def has_buttons(self) -> bool:
        return self._listener is not None

    def poll(self) -> PointerState:
        from PySide6.QtGui import QCursor
        p = QCursor.pos()
        with self._lock:
            b = dict(self._buttons)
        return PointerState(p.x(), p.y(), b["left"], b["right"], b["middle"])

    def close(self) -> None:
        if self._listener is not None:
            self._listener.stop()


def make_pointer_source() -> PointerSource:
    if sys.platform == "win32":
        try:
            return WindowsPointer()
        except Exception:  # noqa: BLE001
            pass
    return QtPointer()
