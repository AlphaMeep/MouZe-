"""Per-user locations for settings, skins and generated cursor files."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("MOUZE_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "MouZe"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MouZe"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "mouze"


def skins_dir() -> Path:
    return config_dir() / "skins"


def generated_dir() -> Path:
    """Where rendered cursor files for the active skin are written."""
    if sys.platform == "win32" and not os.environ.get("MOUZE_HOME"):
        base = Path(os.environ.get("LOCALAPPDATA") or config_dir())
        return base / "MouZe" / "applied"
    return config_dir() / "applied"


def settings_file() -> Path:
    return config_dir() / "settings.json"


def ensure_dirs() -> None:
    for d in (config_dir(), skins_dir(), generated_dir()):
        d.mkdir(parents=True, exist_ok=True)
