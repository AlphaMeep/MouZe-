"""Community skin catalogs: MouZe's open answer to the Steam Workshop.

A catalog is a plain JSON file that anyone can host (a GitHub repo works
well)::

    {
      "name": "MouZe Community",
      "skins": [
        {"id": "sakura-glass", "name": "Sakura Glass", "author": "someone",
         "description": "...", "category": "Glass", "tags": ["pink"],
         "version": "1.0", "updated": "2026-10-13", "animated": false,
         "url": "skins/sakura-glass.mouzeskin", "preview": "previews/sakura-glass.png"}
      ]
    }

``url`` and ``preview`` may be relative to the catalog.  The download can be a
``.mouzeskin`` file or anything else MouZe can import (zip, .cape, ...).

*Subscribing* downloads a skin into your library and keeps it updated: when the
catalog lists a newer ``version``, MouZe downloads it again.  Subscriptions are
remembered in your settings and do not need any account.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CATALOG = "https://raw.githubusercontent.com/AlphaMeep/MouZe-/main/community/index.json"
MAX_DOWNLOAD = 50 * 1024 * 1024


@dataclass
class CatalogEntry:
    catalog: str
    id: str
    name: str
    url: str
    author: str = "Unknown"
    description: str = ""
    category: str = "Community"
    tags: list[str] = field(default_factory=list)
    version: str = "1.0"
    updated: str = ""
    animated: bool = False
    preview: str = ""

    @property
    def key(self) -> str:
        return f"{self.catalog}#{self.id}"


def _resolve(base: str, ref: str) -> str:
    if not ref:
        return ""
    if base.startswith(("http://", "https://")):
        return urllib.parse.urljoin(base, ref)
    # local catalog (file path)
    p = Path(ref)
    return str(p if p.is_absolute() else Path(base).parent / ref)


def read_bytes(location: str, limit: int = MAX_DOWNLOAD, timeout: float = 20.0) -> bytes:
    if location.startswith(("http://", "https://")):
        req = urllib.request.Request(location, headers={"User-Agent": "MouZe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - http(s) only
            data = resp.read(limit + 1)
    else:
        if location.startswith("file://"):
            location = urllib.parse.unquote(urllib.parse.urlparse(location).path)
        data = Path(location).read_bytes()
    if len(data) > limit:
        raise ValueError("download is larger than 50 MB")
    return data


def fetch_catalog(location: str) -> tuple[str, list[CatalogEntry]]:
    """Return (catalog name, entries)."""
    raw = json.loads(read_bytes(location, limit=5_000_000).decode("utf-8-sig"))
    entries = []
    for d in raw.get("skins") or []:
        if not isinstance(d, dict) or not d.get("id") or not d.get("url"):
            continue
        entries.append(CatalogEntry(
            catalog=location, id=str(d["id"]), name=str(d.get("name") or d["id"]),
            url=_resolve(location, str(d["url"])), author=str(d.get("author") or "Unknown"),
            description=str(d.get("description") or ""), category=str(d.get("category") or "Community"),
            tags=[str(t) for t in d.get("tags") or []], version=str(d.get("version") or "1.0"),
            updated=str(d.get("updated") or ""), animated=bool(d.get("animated")),
            preview=_resolve(location, str(d.get("preview") or ""))))
    return str(raw.get("name") or location), entries


def _download_to_library(entry: CatalogEntry, skins_dir: Path) -> Path:
    from .formats.packs import import_path
    data = read_bytes(entry.url)
    name = Path(urllib.parse.urlparse(entry.url).path).name or f"{entry.id}.mouzeskin"
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / name
        f.write_bytes(data)
        staging = Path(tmp) / "out"
        dest = import_path(f, staging, name=entry.name, tags=list(entry.tags) + ["community"],
                           extra={"source": {"catalog": entry.catalog, "id": entry.id, "version": entry.version}})
        final = skins_dir / f"community-{_safe(entry.id)}"
        if final.exists():
            shutil.rmtree(final)
        skins_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), final)
    return final


def _safe(text: str) -> str:
    from .skin import slugify
    return slugify(text)


def subscribe(entry: CatalogEntry, settings, skins_dir: Path) -> Path:
    folder = _download_to_library(entry, skins_dir)
    settings["subscriptions"][entry.key] = {"catalog": entry.catalog, "id": entry.id, "name": entry.name,
                                            "version": entry.version, "folder": folder.name}
    settings.save()
    return folder


def unsubscribe(key: str, settings, skins_dir: Path) -> None:
    sub = settings["subscriptions"].pop(key, None)
    settings.save()
    if sub and sub.get("folder"):
        folder = skins_dir / sub["folder"]
        if folder.is_dir() and folder.parent.resolve() == skins_dir.resolve():
            shutil.rmtree(folder)


def update_subscriptions(settings, skins_dir: Path) -> list[str]:
    """Re-download subscribed skins whose catalog version changed.  Returns updated names."""
    subs = settings["subscriptions"]
    updated = []
    catalogs = {s["catalog"] for s in subs.values()}
    for cat in catalogs:
        try:
            _name, entries = fetch_catalog(cat)
        except Exception:  # noqa: BLE001 - offline is fine
            continue
        for e in entries:
            sub = subs.get(e.key)
            if sub is None:
                continue
            missing = not (skins_dir / sub.get("folder", "")).is_dir()
            if sub.get("version") != e.version or missing:
                try:
                    subscribe(e, settings, skins_dir)
                    updated.append(e.name)
                except Exception:  # noqa: BLE001
                    continue
    return updated
