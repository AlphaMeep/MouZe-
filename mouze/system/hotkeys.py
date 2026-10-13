"""Global hotkeys.

* Windows: ``RegisterHotKey`` on a background thread (hook-free).
* Other platforms: the optional ``pynput`` package, if installed.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

MODIFIERS = {"ctrl": 0x0002, "control": 0x0002, "alt": 0x0001, "shift": 0x0004,
             "win": 0x0008, "super": 0x0008, "meta": 0x0008, "cmd": 0x0008}
MOD_NOREPEAT = 0x4000

VK_NAMES = {
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "space": 0x20, "enter": 0x0D,
    "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "home": 0x24, "end": 0x23, "pageup": 0x21,
    "pagedown": 0x22, "insert": 0x2D, "delete": 0x2E, "backspace": 0x08,
    "plus": 0xBB, "minus": 0xBD, "comma": 0xBC, "period": 0xBE,
}


def parse_hotkey(text: str) -> tuple[set[str], str]:
    """``"ctrl+alt+e"`` -> ({"ctrl", "alt"}, "e")."""
    parts = [p.strip().lower() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("empty hotkey")
    mods = set()
    key = None
    for p in parts:
        if p in MODIFIERS:
            mods.add({"control": "ctrl", "super": "win", "meta": "win", "cmd": "win"}.get(p, p))
        else:
            if key is not None:
                raise ValueError(f"hotkey has two keys: {text}")
            key = p
    if key is None:
        raise ValueError(f"hotkey has no key: {text}")
    return mods, key


def vk_code(key: str) -> int:
    if key in VK_NAMES:
        return VK_NAMES[key]
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x70 + int(key[1:]) - 1
    raise ValueError(f"unknown key: {key}")


def to_pynput(text: str) -> str:
    mods, key = parse_hotkey(text)
    order = ["ctrl", "alt", "shift", "win"]
    names = {"ctrl": "<ctrl>", "alt": "<alt>", "shift": "<shift>", "win": "<cmd>"}
    special = {"left": "left", "right": "right", "up": "up", "down": "down", "space": "space",
               "enter": "enter", "tab": "tab", "esc": "esc", "escape": "esc", "home": "home",
               "end": "end", "pageup": "page_up", "pagedown": "page_down", "insert": "insert",
               "delete": "delete", "backspace": "backspace"}
    if key in special:
        k = f"<{special[key]}>"
    elif key.startswith("f") and key[1:].isdigit():
        k = f"<{key}>"
    elif len(key) == 1:
        k = key
    else:
        raise ValueError(f"unknown key: {key}")
    return "+".join([names[m] for m in order if m in mods] + [k])


class HotkeyManager:
    """Register hotkeys and call ``callback(action)`` when one fires.

    ``callback`` is invoked on a background thread; GUI code should marshal it
    to the main thread (the app uses a Qt signal for that).
    """

    def __init__(self, callback: Callable[[str], None]):
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id = None
        self._pynput = None
        self.failed: dict[str, str] = {}

    def start(self, bindings: dict[str, str]) -> None:
        self.stop()
        self.failed = {}
        valid = {}
        for action, combo in bindings.items():
            if not combo:
                continue
            try:
                parse_hotkey(combo)
                valid[action] = combo
            except ValueError as exc:
                self.failed[action] = str(exc)
        if not valid:
            return
        if sys.platform == "win32":
            self._start_windows(valid)
        else:
            self._start_pynput(valid)

    def stop(self) -> None:
        if self._thread is not None and self._thread_id is not None and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = None
        if self._pynput is not None:
            try:
                self._pynput.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pynput = None

    # Windows --------------------------------------------------------------------
    def _start_windows(self, bindings: dict[str, str]) -> None:  # pragma: no cover - Windows only
        ready = threading.Event()

        def run():
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            self._thread_id = kernel32.GetCurrentThreadId()
            ids = {}
            for i, (action, combo) in enumerate(bindings.items(), start=1):
                mods, key = parse_hotkey(combo)
                try:
                    vk = vk_code(key)
                except ValueError as exc:
                    self.failed[action] = str(exc)
                    continue
                flags = MOD_NOREPEAT
                for m in mods:
                    flags |= MODIFIERS[m]
                if user32.RegisterHotKey(None, i, flags, vk):
                    ids[i] = action
                else:
                    self.failed[action] = f"{combo} is already used by another program"
            ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and msg.wParam in ids:  # WM_HOTKEY
                    try:
                        self.callback(ids[msg.wParam])
                    except Exception:  # noqa: BLE001
                        log.exception("hotkey callback failed")
            for i in ids:
                user32.UnregisterHotKey(None, i)

        self._thread = threading.Thread(target=run, name="mouze-hotkeys", daemon=True)
        self._thread.start()
        ready.wait(2)

    # pynput ---------------------------------------------------------------------
    def _start_pynput(self, bindings: dict[str, str]) -> None:
        try:
            from pynput import keyboard
        except Exception:  # noqa: BLE001
            for action in bindings:
                self.failed[action] = "global hotkeys need the optional 'pynput' package on this platform"
            return
        mapping = {}
        for action, combo in bindings.items():
            try:
                mapping[to_pynput(combo)] = (lambda a=action: self.callback(a))
            except ValueError as exc:
                self.failed[action] = str(exc)
        try:
            self._pynput = keyboard.GlobalHotKeys(mapping)
            self._pynput.daemon = True
            self._pynput.start()
        except Exception as exc:  # noqa: BLE001
            for action in bindings:
                self.failed[action] = f"could not register hotkeys: {exc}"
            self._pynput = None
