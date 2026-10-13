"""Windows backend.

Uses only documented, hook-free APIs - exactly what *Mouse Properties > Pointers*
does: write the cursor file paths to ``HKCU\\Control Panel\\Cursors`` and call
``SystemParametersInfo(SPI_SETCURSORS)``.  Nothing is injected into other
processes, so it is safe to use alongside anti-cheat protected games.
"""

from __future__ import annotations

import json
import sys
import time

from .. import paths
from ..formats import wincursor
from ..imaging import Adjustments
from ..roles import WINDOWS_IDC, WINDOWS_REG_NAMES, WINDOWS_SCHEME_ORDER, Role
from ..skin import Skin
from .base import Backend, BackendError

if sys.platform == "win32":  # pragma: no cover - exercised on Windows only
    import ctypes
    import winreg
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    SPI_SETCURSORS = 0x0057
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02

    class CURSORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("hCursor", wintypes.HANDLE), ("ptScreenPos", wintypes.POINT)]

    user32.LoadCursorW.restype = wintypes.HANDLE
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
    user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
    user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT]

CURSORS_KEY = r"Control Panel\Cursors"
BACKUP_NAME = "windows_cursor_backup.json"
SCHEME_NAME = "MouZe"


def dpi_scale() -> float:
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:  # noqa: BLE001
        return 1.0


class WindowsBackend(Backend):
    name = "windows"
    supports_native = True
    supports_role_detection = True
    notes = "Applies cursors through the standard Windows pointer scheme (no hooks, no injection)."

    def __init__(self):
        self._handles: dict[int, Role] = {}
        self._handles_at = 0.0

    # registry -------------------------------------------------------------------
    def _read_values(self) -> dict:
        values = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CURSORS_KEY) as key:
            for name in ["", "Scheme Source", "CursorBaseSize", *WINDOWS_REG_NAMES.values()]:
                try:
                    val, typ = winreg.QueryValueEx(key, name)
                    values[name] = [val, typ]
                except FileNotFoundError:
                    values[name] = None
        return values

    def _write_values(self, values: dict) -> None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CURSORS_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name, entry in values.items():
                if entry is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, name, 0, entry[1], entry[0])

    def _backup_path(self):
        return paths.config_dir() / BACKUP_NAME

    def _ensure_backup(self) -> None:
        bp = self._backup_path()
        if bp.exists():
            return
        current = self._read_values()
        if (current.get("") or [None])[0] == SCHEME_NAME:
            return  # already ours (e.g. backup deleted); nothing sensible to save
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_text(json.dumps(current, indent=2), "utf-8")

    def _reload(self) -> None:
        # Retry without the WM_SETTINGCHANGE broadcast, which can fail when some window is hung.
        for flags in (SPIF_UPDATEINIFILE | SPIF_SENDCHANGE, SPIF_UPDATEINIFILE):
            if user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, flags):
                self._handles_at = 0.0
                return
        raise BackendError(
            f"Windows refused to reload the cursors (error {ctypes.get_last_error()}). The new cursors are "
            "saved and will appear after you sign out and back in.")

    # API ----------------------------------------------------------------------
    def apply(self, skin: Skin, size: int, adj: Adjustments | None = None) -> str:
        out = self.output_dir(skin, size, adj)
        out.mkdir(parents=True, exist_ok=True)
        scale = dpi_scale()
        sizes = sorted({size, min(256, round(size * scale))})
        values = {"": [SCHEME_NAME, winreg.REG_SZ], "Scheme Source": [1, winreg.REG_DWORD]}
        for role in WINDOWS_SCHEME_ORDER:
            path = write_multisize(skin, role, sizes, adj, out)
            values[WINDOWS_REG_NAMES[role]] = [str(path), winreg.REG_EXPAND_SZ]
        values["CursorBaseSize"] = [int(size), winreg.REG_DWORD]
        self._ensure_backup()
        self._write_values(values)
        self._reload()
        self.clean_generated(keep=out)
        return f"Applied '{skin.name}' at {size}px."

    def restore_default(self, previous: bool = True) -> str:
        bp = self._backup_path()
        if previous and bp.exists():
            values = json.loads(bp.read_text("utf-8"))
            self._write_values(values)
            msg = "Restored your previous cursors."
        else:
            values = {name: ["", winreg.REG_EXPAND_SZ] for name in WINDOWS_REG_NAMES.values()}
            values[""] = ["Windows Default", winreg.REG_SZ]
            values["Scheme Source"] = [2, winreg.REG_DWORD]
            values["CursorBaseSize"] = None
            self._write_values(values)
            msg = "Restored the Windows default cursors."
        self._reload()
        if bp.exists():
            bp.unlink()
        self.clean_generated(keep=None)
        return msg

    def hide(self) -> str:
        from PIL import Image
        out = paths.generated_dir() / "hidden"
        out.mkdir(parents=True, exist_ok=True)
        blank = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        values = {"": [SCHEME_NAME, winreg.REG_SZ]}
        for role in WINDOWS_SCHEME_ORDER:
            # one file per role so Windows keeps distinct handles (needed for role detection)
            p = out / f"{role.value}.cur"
            p.write_bytes(wincursor.write_cur(wincursor.CursorImage(blank, (0, 0))))
            values[WINDOWS_REG_NAMES[role]] = [str(p), winreg.REG_EXPAND_SZ]
        self._ensure_backup()
        self._write_values(values)
        self._reload()
        return "System cursor hidden (overlay cursor active)."

    def current_role(self) -> Role | None:
        now = time.monotonic()
        if now - self._handles_at > 2.0:
            self._handles = {}
            for role, idc in WINDOWS_IDC.items():
                h = user32.LoadCursorW(None, ctypes.c_void_p(idc))
                if h:
                    self._handles.setdefault(int(h), role)
            self._handles_at = now
        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(CURSORINFO)
        if not user32.GetCursorInfo(ctypes.byref(info)):
            return None
        if not info.flags & 1:  # CURSOR_SHOWING
            return None
        return self._handles.get(int(info.hCursor or 0), Role.ARROW)


def write_multisize(skin: Skin, role: Role, sizes: list[int], adj, out_dir):
    """Write ``role`` as .cur/.ani holding every size in ``sizes`` (for HiDPI)."""
    anims = [skin.render(role, s, adj) for s in sizes]
    base = out_dir / role.value
    first = anims[0]
    if first.animated:
        frames = []
        for i in range(len(first.frames)):
            frames.append([wincursor.CursorImage(a.frames[min(i, len(a.frames) - 1)], a.hotspot) for a in anims])
        data = _write_ani_multisize(frames, first.delays, skin.name, skin.meta.author)
        path = base.with_suffix(".ani")
    else:
        data = wincursor.write_cur([wincursor.CursorImage(a.frames[0], a.hotspot) for a in anims])
        path = base.with_suffix(".cur")
    path.write_bytes(data)
    return path


def _write_ani_multisize(frames, delays, title, author) -> bytes:
    import struct
    n = len(frames)
    jiffies = [max(1, round(d * 60 / 1000)) for d in delays]
    w, h = frames[0][0].image.size
    chunk = wincursor._chunk
    body = chunk(b"anih", struct.pack("<9I", 36, n, n, w, h, 32, 1, jiffies[0], 0x1))
    if len(set(jiffies)) > 1:
        body += chunk(b"rate", struct.pack(f"<{n}I", *jiffies))
    body += chunk(b"LIST", b"fram" + b"".join(chunk(b"icon", wincursor.write_cur(f)) for f in frames))
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"ACON" + body
