"""Persistent settings stored as JSON in the user's config directory."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

from . import paths

DEFAULT_HOTKEYS = {
    "toggle_effects": "ctrl+alt+e",
    "next_skin": "ctrl+alt+right",
    "prev_skin": "ctrl+alt+left",
    "size_up": "ctrl+alt+up",
    "size_down": "ctrl+alt+down",
    "restore_default": "ctrl+alt+r",
    "locate": "ctrl+alt+l",
    "spotlight": "ctrl+alt+s",
    "show_window": "ctrl+alt+m",
}

HOTKEY_LABELS = {
    "toggle_effects": "Toggle effects overlay",
    "next_skin": "Next favourite skin",
    "prev_skin": "Previous favourite skin",
    "size_up": "Cursor size up",
    "size_down": "Cursor size down",
    "restore_default": "Panic: restore system cursors",
    "locate": "Locate cursor",
    "spotlight": "Toggle spotlight",
    "show_window": "Show MouZe window",
}

DEFAULTS: dict = {
    "version": 1,
    "skin": "builtin:classic-light",
    "size": 32,
    "adjustments": {},
    "favorites": [],
    "recent": [],
    "apply_on_start": True,
    "restore_on_exit": False,
    "start_minimized": False,
    "minimize_to_tray": True,
    "hotkeys_enabled": True,
    "hotkeys": DEFAULT_HOTKEYS,
    "effects": {
        "enabled": False,
        "fps": 120,
        "pause_fullscreen": True,
        "overlay_cursor": False,
        "trail": {"enabled": True, "style": "ribbon", "color": "#00e5ff", "rainbow": True,
                  "length": 18, "width": 6},
        "clicks": {"enabled": True, "style": "ripple", "left": "#00e5ff", "right": "#ff2bd6",
                   "middle": "#ffea00", "size": 38, "duration": 450},
        "halo": {"enabled": False, "color": "#ffeb3b", "radius": 30, "opacity": 0.35},
        "spotlight": {"enabled": False, "radius": 160, "dim": 0.6},
        "locator": {"shake": True, "sensitivity": 5, "color": "#ff4081"},
    },
    "profiles": {"enabled": True, "rules": []},
    "skin_sizes": {},            # per-skin size overrides (skin id -> px)
    "language": "auto",
    "silent_running": False,     # start hidden in the tray, no notifications
    "catalogs": ["https://raw.githubusercontent.com/AlphaMeep/MouZe-/main/community/index.json"],
    "subscriptions": {},
    "auto_update_subscriptions": True,
    "refresh_on_display_change": True,
    "shuffle": {"enabled": False, "minutes": 30, "favorites_only": True},
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("adjustments", "skin_sizes",
                                                                               "subscriptions"):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.settings_file()
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
            self.data = deep_merge(DEFAULTS, raw)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # Keep a copy of the unreadable file instead of silently losing it.
            try:
                self.path.replace(self.path.with_suffix(".broken.json"))
            except OSError:
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    # convenience accessors ----------------------------------------------------
    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

    def adjustments_for(self, skin_id: str) -> dict:
        return dict(self.data["adjustments"].get(skin_id, {}))

    def set_adjustments(self, skin_id: str, adj: dict) -> None:
        if adj:
            self.data["adjustments"][skin_id] = adj
        else:
            self.data["adjustments"].pop(skin_id, None)

    def toggle_favorite(self, skin_id: str) -> bool:
        favs = self.data["favorites"]
        if skin_id in favs:
            favs.remove(skin_id)
            return False
        favs.append(skin_id)
        return True

    def push_recent(self, skin_id: str) -> None:
        rec = [s for s in self.data["recent"] if s != skin_id]
        self.data["recent"] = [skin_id] + rec[:19]
