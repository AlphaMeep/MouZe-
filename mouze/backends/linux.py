"""Linux / BSD backend: build an Xcursor theme and switch the desktop to it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .. import paths
from ..formats.packs import export_xcursor_theme
from ..imaging import Adjustments
from ..skin import Skin, slugify
from .base import Backend, BackendError

THEME_PREFIX = "mouze-"
STATE_FILE = "linux_cursor_backup.json"


def _run(*cmd: str, timeout: float = 8.0) -> tuple[bool, str]:
    if not shutil.which(cmd[0]):
        return False, ""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode == 0, res.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False, ""


def icons_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "icons"


def desktop() -> str:
    return (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()


GSETTINGS_SCHEMAS = {
    "cinnamon": ("org.cinnamon.desktop.interface", "cursor-theme", "cursor-size"),
    "mate": ("org.mate.peripherals-mouse", "cursor-theme", "cursor-size"),
    "gnome": ("org.gnome.desktop.interface", "cursor-theme", "cursor-size"),
}


class LinuxBackend(Backend):
    name = "linux"
    supports_native = True
    notes = ("Installs the skin as an Xcursor theme in ~/.local/share/icons and switches your "
             "desktop to it. Some apps only pick up the change after they restart.")

    def _gsettings(self) -> tuple[str, str, str]:
        d = desktop()
        for key, schema in GSETTINGS_SCHEMAS.items():
            if key in d:
                return schema
        return GSETTINGS_SCHEMAS["gnome"]

    def current_theme(self) -> tuple[str | None, int | None]:
        schema, theme_key, size_key = self._gsettings()
        ok, theme = _run("gsettings", "get", schema, theme_key)
        ok2, size = _run("gsettings", "get", schema, size_key)
        if ok:
            return theme.strip("'\""), int(size) if ok2 and size.isdigit() else None
        if "kde" in desktop() or "plasma" in desktop():
            ok, theme = _run("kreadconfig6", "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorTheme")
            if not ok:
                ok, theme = _run("kreadconfig5", "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorTheme")
            return (theme or None), None
        ok, theme = _run("xfconf-query", "-c", "xsettings", "-p", "/Gtk/CursorThemeName")
        if ok:
            return theme, None
        return os.environ.get("XCURSOR_THEME"), None

    def _state_path(self) -> Path:
        return paths.config_dir() / STATE_FILE

    def _save_previous(self) -> None:
        sp = self._state_path()
        if sp.exists():
            return
        theme, size = self.current_theme()
        if theme and theme.startswith(THEME_PREFIX):
            return
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps({"theme": theme, "size": size}), "utf-8")

    def set_theme(self, name: str, size: int | None) -> list[str]:
        """Ask every desktop/tool we know about to use cursor theme ``name``."""
        done = []
        d = desktop()
        schema, theme_key, size_key = self._gsettings()
        if _run("gsettings", "set", schema, theme_key, name)[0]:
            done.append("gsettings")
            if size:
                _run("gsettings", "set", schema, size_key, str(size))
        if "kde" in d or "plasma" in d:
            if size:
                for tool in ("kwriteconfig6", "kwriteconfig5"):
                    if _run(tool, "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorSize", str(size))[0]:
                        break
            if _run("plasma-apply-cursortheme", name)[0]:
                done.append("plasma")
        if "xfce" in d:
            if _run("xfconf-query", "-c", "xsettings", "-p", "/Gtk/CursorThemeName", "-s", name)[0]:
                done.append("xfconf")
            if size:
                _run("xfconf-query", "-c", "xsettings", "-p", "/Gtk/CursorThemeSize", "-s", str(size))
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            if _run("hyprctl", "setcursor", name, str(size or 24))[0]:
                done.append("hyprland")
        if os.environ.get("SWAYSOCK"):
            if _run("swaymsg", "seat", "*", "xcursor_theme", name, str(size or 24))[0]:
                done.append("sway")
        # Generic fallback used by plain X11 window managers and as a default.
        default_dir = Path.home() / ".icons" / "default"
        default_dir.mkdir(parents=True, exist_ok=True)
        (default_dir / "index.theme").write_text(f"[Icon Theme]\nName=Default\nInherits={name}\n", "utf-8")
        if os.environ.get("DISPLAY"):
            if size:
                _run("sh", "-c", f"printf 'Xcursor.theme: %s\\nXcursor.size: %s\\n' '{name}' '{int(size)}' | xrdb -merge")
            else:
                _run("sh", "-c", f"printf 'Xcursor.theme: %s\\n' '{name}' | xrdb -merge")
            if _run("xsetroot", "-cursor_name", "left_ptr")[0]:
                done.append("xsetroot")
        return done

    def apply(self, skin: Skin, size: int, adj: Adjustments | None = None) -> str:
        self._save_previous()
        base = icons_dir()
        base.mkdir(parents=True, exist_ok=True)
        # A new name per size/adjustment combo makes desktops notice the change.
        theme = f"{THEME_PREFIX}{slugify(skin.name)[:40]}-{self.output_dir(skin, size, adj).name[-8:]}"
        sizes = sorted({24, 32, 48, 64, 96, size, size * 2})
        sizes = [s for s in sizes if s <= 256]
        export_xcursor_theme(skin, base, theme, sizes=sizes, adj=adj)
        legacy = Path.home() / ".icons" / theme
        if not legacy.exists():
            legacy.parent.mkdir(parents=True, exist_ok=True)
            try:
                legacy.symlink_to(base / theme, target_is_directory=True)
            except OSError:
                pass
        # Remove themes from previously applied skins.
        for d in base.glob(f"{THEME_PREFIX}*"):
            if d.name != theme:
                shutil.rmtree(d, ignore_errors=True)
                stale = Path.home() / ".icons" / d.name
                if stale.is_symlink():
                    stale.unlink()
        done = self.set_theme(theme, size)
        if not done:
            raise BackendError(
                f"Installed the cursor theme '{theme}' but could not find a way to switch to it "
                "automatically. Select it in your desktop's appearance settings.")
        return f"Applied '{skin.name}' at {size}px ({', '.join(done)})."

    def restore_default(self, previous: bool = True) -> str:
        sp = self._state_path()
        theme, size = None, None
        if previous and sp.exists():
            data = json.loads(sp.read_text("utf-8"))
            theme, size = data.get("theme"), data.get("size")
        if not theme:
            d = desktop()
            theme = "breeze_cursors" if ("kde" in d or "plasma" in d) else "Adwaita"
        self.set_theme(theme, size or 24)
        if sp.exists():
            sp.unlink()
        for d in icons_dir().glob(f"{THEME_PREFIX}*"):
            shutil.rmtree(d, ignore_errors=True)
            stale = Path.home() / ".icons" / d.name
            if stale.is_symlink():
                stale.unlink()
        return f"Restored cursor theme '{theme}'."
