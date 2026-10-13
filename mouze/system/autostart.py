"""Start MouZe when the user logs in."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MouZe"


def launch_command() -> list[str]:
    if getattr(sys, "frozen", False):  # PyInstaller build
        return [sys.executable, "--minimized"]
    exe = sys.executable
    if sys.platform == "win32" and exe.lower().endswith("python.exe"):
        pyw = exe[:-10] + "pythonw.exe"
        if os.path.exists(pyw):
            exe = pyw
    return [exe, "-m", "mouze", "--minimized"]


def _quote(parts: list[str]) -> str:
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


def _desktop_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / "mouze.desktop"


def _plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "io.github.mouze.plist"


def is_enabled() -> bool:
    if sys.platform == "win32":  # pragma: no cover
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except FileNotFoundError:
            return False
    if sys.platform == "darwin":
        return _plist().exists()
    return _desktop_file().exists()


def set_enabled(enabled: bool) -> None:
    cmd = launch_command()
    if sys.platform == "win32":  # pragma: no cover
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _quote(cmd))
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return
    if sys.platform == "darwin":
        p = _plist()
        if enabled:
            p.parent.mkdir(parents=True, exist_ok=True)
            args = "".join(f"<string>{a}</string>" for a in cmd)
            p.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0"><dict><key>Label</key><string>io.github.mouze</string>'
                f"<key>ProgramArguments</key><array>{args}</array>"
                "<key>RunAtLoad</key><true/></dict></plist>\n", "utf-8")
        elif p.exists():
            p.unlink()
        return
    f = _desktop_file()
    if enabled:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("[Desktop Entry]\nType=Application\nName=MouZe\n"
                     f"Exec={_quote(cmd)}\nX-GNOME-Autostart-enabled=true\n"
                     "Comment=Custom mouse cursors and cursor effects\n", "utf-8")
    elif f.exists():
        f.unlink()
