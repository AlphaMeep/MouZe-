"""Skin library: built-in skins plus everything in the user's skins folder."""

from __future__ import annotations

import logging
import random
import shutil
from pathlib import Path

from . import paths
from .builtin.catalog import CATEGORIES, builtin_skins
from .skin import SKIN_EXT, Skin, load_skin

log = logging.getLogger(__name__)


class SkinLibrary:
    def __init__(self, user_dir: Path | None = None):
        self.user_dir = user_dir or paths.skins_dir()
        self._skins: dict[str, Skin] = {}
        self.errors: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._skins = {s.id: s for s in builtin_skins()}
        self.errors.clear()
        if self.user_dir.is_dir():
            for entry in sorted(self.user_dir.iterdir()):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir() and (entry / "skin.json").exists() or entry.suffix.lower() == SKIN_EXT:
                    sid = f"user:{entry.stem if entry.is_file() else entry.name}"
                    try:
                        self._skins[sid] = load_skin(entry, sid)
                    except Exception as exc:  # noqa: BLE001 - one bad skin must not break the app
                        log.warning("could not load skin %s: %s", entry, exc)
                        self.errors[str(entry)] = str(exc)

    def __len__(self) -> int:
        return len(self._skins)

    def __iter__(self):
        return iter(self._skins.values())

    def __contains__(self, skin_id: str) -> bool:
        return skin_id in self._skins

    def get(self, skin_id: str) -> Skin | None:
        return self._skins.get(skin_id)

    def all(self) -> list[Skin]:
        return list(self._skins.values())

    def categories(self) -> list[str]:
        cats = list(CATEGORIES)
        for s in self._skins.values():
            if s.meta.category not in cats:
                cats.append(s.meta.category)
        return cats

    def search(self, text: str = "", category: str | None = None, animated: bool | None = None,
               ids: list[str] | None = None) -> list[Skin]:
        words = text.lower().split()
        out = []
        pool = [self._skins[i] for i in ids if i in self._skins] if ids is not None else self._skins.values()
        for s in pool:
            if category and s.meta.category != category:
                continue
            if animated is not None and s.animated != animated:
                continue
            hay = " ".join([s.name, s.meta.author, s.meta.category, s.meta.description, *s.meta.tags]).lower()
            if all(w in hay for w in words):
                out.append(s)
        return out

    def random(self, pool: list[str] | None = None, exclude: str | None = None) -> Skin | None:
        ids = [i for i in (pool or list(self._skins)) if i in self._skins and i != exclude]
        return self._skins[random.choice(ids)] if ids else None

    def add_from_path(self, path: Path) -> Skin:
        sid = f"user:{path.stem if path.is_file() else path.name}"
        skin = load_skin(path, sid)
        self._skins[sid] = skin
        return skin

    def delete(self, skin_id: str) -> None:
        skin = self._skins.get(skin_id)
        if skin is None or skin.is_builtin or skin.path is None:
            raise ValueError("only user skins can be deleted")
        if skin.path.is_dir():
            shutil.rmtree(skin.path)
        else:
            skin.path.unlink()
        del self._skins[skin_id]
