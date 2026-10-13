"""Import skins you have from **Mouse X** (Steam app 4255580) and other Steam
cursor apps.

Steam stores subscribed Workshop items locally in
``<library>/steamapps/workshop/content/<appid>/<item id>/``.  This module finds
every Steam library on the machine, lists those items, optionally looks up
their titles with the public Steam Web API, and imports them through MouZe's
generic importer.  The importer understands images, frame sequences, GIF,
APNG, AVIF, SVG, CUR and ANI, and reads hotspot/speed hints from any metadata
files it finds.

Mouse X has not published its skin format, so the import is best-effort.  If
a hotspot ends up wrong, fix it in Studio, Pack Builder ("Open existing skin").

Workshop skins belong to their creators.  MouZe only converts the copies that
are already on your computer for your own use and never uploads or shares
them.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from ..skin import SUPPORTED_EXTS

MOUSE_X_APPID = 4255580
# Other Steam cursor apps whose Workshop items are plain image/cursor files.
OTHER_APPS = {
    4342760: "Custom Cursor",
    2201210: "Cursor Engine",
}
KNOWN_APPS = {MOUSE_X_APPID: "Mouse X", **OTHER_APPS}
STEAM_DETAILS_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"


@dataclass
class WorkshopItem:
    appid: int
    item_id: str
    path: Path
    title: str = ""
    author: str = ""
    preview: Path | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def app_name(self) -> str:
        return KNOWN_APPS.get(self.appid, f"Steam app {self.appid}")

    @property
    def display_name(self) -> str:
        return self.title or f"{self.app_name} item {self.item_id}"


# ------------------------------------------------------------------------- Steam paths

def steam_roots() -> list[Path]:
    """Every place a Steam installation is commonly found."""
    cands: list[Path] = []
    env = os.environ.get("MOUZE_STEAM_PATH")
    if env:
        cands += [Path(p) for p in env.split(os.pathsep) if p]
    if sys.platform == "win32":  # pragma: no cover - Windows only
        try:
            import winreg
            for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                     (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                     (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        cands.append(Path(winreg.QueryValueEx(k, value)[0]))
                except OSError:
                    pass
        except ImportError:
            pass
        for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
            if os.environ.get(env_name):
                cands.append(Path(os.environ[env_name]) / "Steam")
    elif sys.platform == "darwin":
        cands.append(Path.home() / "Library" / "Application Support" / "Steam")
    else:
        home = Path.home()
        cands += [home / ".steam" / "steam", home / ".steam" / "root", home / ".local" / "share" / "Steam",
                  home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
                  home / "snap" / "steam" / "common" / ".local" / "share" / "Steam"]
    out, seen = [], set()
    for c in cands:
        try:
            r = c.resolve()
        except OSError:
            continue
        if r.is_dir() and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def parse_library_folders(vdf_text: str) -> list[Path]:
    paths = re.findall(r'"path"\s+"([^"]+)"', vdf_text)
    return [Path(p.replace("\\\\", "\\")) for p in paths]


def library_folders() -> list[Path]:
    libs: list[Path] = []
    for root in steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                libs += parse_library_folders(vdf.read_text("utf-8", "replace"))
            except OSError:
                pass
    out, seen = [], set()
    for lib in libs:
        try:
            r = lib.resolve()
        except OSError:
            continue
        if (r / "steamapps").is_dir() and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _has_cursor_files(folder: Path) -> bool:
    for p in folder.rglob("*"):
        if p.is_file() and (p.suffix.lower() in SUPPORTED_EXTS | {".cape", ".css"} or p.name == "skin.json"):
            return True
    return False


def _local_meta(folder: Path) -> tuple[str, str, Path | None]:
    """Title, author and preview image from files inside an item folder, if any."""
    title = author = ""
    for js in sorted(folder.rglob("*.json"))[:20]:
        try:
            data = json.loads(js.read_text("utf-8-sig", "replace"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            low = {str(k).lower(): v for k, v in data.items()}
            title = title or str(low.get("title") or low.get("name") or "")
            author = author or str(low.get("author") or low.get("creator") or "")
    preview = None
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp") and \
                any(w in p.stem.lower() for w in ("preview", "thumb", "cover")):
            preview = p
            break
    return title, author, preview


def find_workshop_items(appids=(MOUSE_X_APPID,), extra_dirs: list[Path] | None = None) -> list[WorkshopItem]:
    """List downloaded Workshop items for the given Steam apps (Mouse X by default)."""
    items: list[WorkshopItem] = []
    for lib in library_folders():
        for appid in appids:
            content = lib / "steamapps" / "workshop" / "content" / str(appid)
            if not content.is_dir():
                continue
            for d in sorted(content.iterdir()):
                if d.is_dir() and _has_cursor_files(d):
                    title, author, preview = _local_meta(d)
                    items.append(WorkshopItem(appid, d.name, d, title, author, preview))
    for extra in extra_dirs or []:
        if extra.is_dir():
            for d in sorted(extra.iterdir()):
                if d.is_dir() and _has_cursor_files(d):
                    title, author, preview = _local_meta(d)
                    items.append(WorkshopItem(MOUSE_X_APPID, d.name, d, title, author, preview))
    return items


def mouse_x_local_skin_dirs() -> list[Path]:
    """Folders where Mouse X may keep skins made in its own editor."""
    out = []
    bases = []
    for env_name in ("APPDATA", "LOCALAPPDATA"):
        if os.environ.get(env_name):
            bases.append(Path(os.environ[env_name]))
    for lib in library_folders():
        bases.append(lib / "steamapps" / "common")
    for base in bases:
        for sub in ("Mouse X", "MouseX", "CenterPoint Gaming/Mouse X", "CenterPointGaming/Mouse X"):
            root = base / sub
            if not root.is_dir():
                continue
            for d in root.rglob("*"):
                if d.is_dir() and d.name.lower() in ("skins", "myskins", "my skins", "custom", "editor", "cursors"):
                    out.append(d)
    return out


def lookup_titles(items: list[WorkshopItem], timeout: float = 10.0) -> int:
    """Fill in titles/authors using Steam's public GetPublishedFileDetails API.

    No API key is needed.  Returns how many items got a title.  Network errors
    are swallowed; the import still works with generic names.
    """
    todo = [i for i in items if not i.title]
    if not todo:
        return 0
    form = {"itemcount": str(len(todo))}
    for n, item in enumerate(todo):
        form[f"publishedfileids[{n}]"] = item.item_id
    data = urllib.parse.urlencode(form).encode()
    try:
        req = urllib.request.Request(STEAM_DETAILS_API, data=data, method="POST",
                                     headers={"User-Agent": "MouZe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https URL
            payload = json.loads(resp.read(5_000_000).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return 0
    found = 0
    by_id = {i.item_id: i for i in todo}
    for d in (payload.get("response") or {}).get("publishedfiledetails") or []:
        item = by_id.get(str(d.get("publishedfileid")))
        if item and d.get("title"):
            item.title = str(d["title"])
            item.tags = [t.get("tag", "") for t in d.get("tags") or [] if isinstance(t, dict)]
            found += 1
    return found


def import_item(item: WorkshopItem, skins_dir: Path) -> Path:
    """Convert one Workshop item into a MouZe skin folder."""
    from .packs import import_path
    tags = ["workshop", item.app_name.lower().replace(" ", "-")] + [t.lower() for t in item.tags if t]
    extra = {"source": {"app": item.app_name, "appid": item.appid, "workshop_id": item.item_id,
                        "note": "Imported from your local Steam Workshop download. Belongs to its creator; "
                                "do not redistribute without permission."}}
    dest = import_path(item.path, skins_dir, name=item.title or None, category=item.app_name, tags=tags,
                       extra=extra)
    if item.author:
        mf = dest / "skin.json"
        data = json.loads(mf.read_text("utf-8"))
        if data.get("author") in (None, "", "Imported", "Unknown"):
            data["author"] = item.author
            mf.write_text(json.dumps(data, indent=2), "utf-8")
    return dest
