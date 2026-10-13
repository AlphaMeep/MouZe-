"""Find out which application is in the foreground (for per-app profiles)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class ForegroundInfo:
    process: str            # executable name, lower-case, e.g. "game.exe" / "firefox"
    fullscreen: bool = False
    title: str = ""


def foreground() -> ForegroundInfo | None:
    try:
        if sys.platform == "win32":
            return _windows()
        if sys.platform == "darwin":
            return _mac()
        return _x11()
    except Exception:  # noqa: BLE001 - best effort only
        return None


def _windows() -> ForegroundInfo | None:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value)
        kernel32.CloseHandle(h)
    length = user32.GetWindowTextLengthW(hwnd)
    tbuf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, tbuf, length + 1)
    # fullscreen = window covers its whole monitor (and is not the desktop/shell)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    mon = user32.MonitorFromWindow(hwnd, 2)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    full = False
    if user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        m = mi.rcMonitor
        full = (rect.left <= m.left and rect.top <= m.top and rect.right >= m.right
                and rect.bottom >= m.bottom)
    if name.lower() in ("explorer.exe", "searchhost.exe", "shellexperiencehost.exe"):
        full = False
    return ForegroundInfo(name.lower(), full, tbuf.value)


def _x11() -> ForegroundInfo | None:
    if not os.environ.get("DISPLAY") or not shutil.which("xprop"):
        return None
    out = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True, text=True,
                         timeout=2).stdout
    wid = out.strip().split()[-1] if out.strip() else ""
    if not wid.startswith("0x") or int(wid, 16) == 0:
        return None
    props = subprocess.run(["xprop", "-id", wid, "_NET_WM_PID", "_NET_WM_STATE", "_NET_WM_NAME"],
                           capture_output=True, text=True, timeout=2).stdout
    pid = None
    full = "_NET_WM_STATE_FULLSCREEN" in props
    title = ""
    for line in props.splitlines():
        if line.startswith("_NET_WM_PID") and "=" in line:
            try:
                pid = int(line.split("=")[1].strip())
            except ValueError:
                pid = None
        elif line.startswith("_NET_WM_NAME") and "=" in line:
            title = line.split("=", 1)[1].strip().strip('"')
    name = ""
    if pid:
        try:
            with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
                name = f.read().strip()
        except OSError:
            name = ""
    return ForegroundInfo(name.lower(), full, title)


def _mac() -> ForegroundInfo | None:  # pragma: no cover - macOS only
    out = subprocess.run(["osascript", "-e",
                          'tell application "System Events" to get name of first application process '
                          'whose frontmost is true'], capture_output=True, text=True, timeout=2).stdout
    name = out.strip()
    return ForegroundInfo(name.lower()) if name else None
