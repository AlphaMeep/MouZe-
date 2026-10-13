"""Skin model: a named set of cursors, one per :class:`~mouze.roles.Role`.

There are two kinds of skins:

* :class:`ProceduralSkin` (see :mod:`mouze.builtin`) - drawn from vector
  recipes, crisp at every size.  All built-in skins are procedural, and the
  Designer in the app saves procedural skins too.
* :class:`FileSkin` - made of image files (PNG, GIF, APNG, WebP, AVIF, SVG,
  CUR, ANI, Xcursor) described by a ``skin.json`` manifest.  This is what
  imports and community skins use.  See ``docs/SKIN_FORMAT.md``.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageSequence

from . import imaging
from .formats import wincursor, xcursor
from .imaging import Adjustments
from .roles import FALLBACKS, Role

SKIN_FORMAT_VERSION = 1
SKIN_EXT = ".mouzeskin"
IMAGE_EXTS = {".png", ".gif", ".webp", ".apng", ".avif", ".bmp", ".jpg", ".jpeg", ".tga"}
CURSOR_EXTS = {".cur", ".ico", ".ani"}
VECTOR_EXTS = {".svg"}
SUPPORTED_EXTS = IMAGE_EXTS | CURSOR_EXTS | VECTOR_EXTS


@dataclass
class CursorAnim:
    """A ready-to-use cursor: equal-sized RGBA frames, per-frame delays, hotspot."""

    frames: list[Image.Image]
    delays: list[int]
    hotspot: tuple[int, int]

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1

    @property
    def size(self) -> tuple[int, int]:
        return self.frames[0].size

    @property
    def duration(self) -> int:
        return sum(self.delays) if self.animated else 0

    def frame_at(self, t_ms: float) -> Image.Image:
        if not self.animated:
            return self.frames[0]
        t = t_ms % max(1, self.duration)
        for frame, d in zip(self.frames, self.delays):
            if t < d:
                return frame
            t -= d
        return self.frames[-1]

    def frame_index_at(self, t_ms: float) -> int:
        if not self.animated:
            return 0
        t = t_ms % max(1, self.duration)
        for i, d in enumerate(self.delays):
            if t < d:
                return i
            t -= d
        return len(self.frames) - 1


@dataclass
class SkinMeta:
    name: str
    author: str = "Unknown"
    category: str = "Custom"
    tags: list[str] = field(default_factory=list)
    description: str = ""
    license: str = ""
    version: str = "1.0"
    animated: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name, "author": self.author, "category": self.category,
            "tags": list(self.tags), "description": self.description,
            "license": self.license, "version": self.version,
        }


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "skin"


class Skin:
    """Base class.  Subclasses implement :meth:`provided_roles` and :meth:`_render`."""

    def __init__(self, skin_id: str, meta: SkinMeta, path: Path | None = None):
        self.id = skin_id
        self.meta = meta
        self.path = path
        self._cache: dict[tuple, CursorAnim] = {}

    # --- to implement -------------------------------------------------------
    def provided_roles(self) -> set[Role]:
        raise NotImplementedError

    def _render(self, role: Role, size: int) -> CursorAnim:
        raise NotImplementedError

    # --- public ---------------------------------------------------------------
    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def is_builtin(self) -> bool:
        return self.id.startswith("builtin:")

    def resolve_role(self, role: Role) -> Role:
        provided = self.provided_roles()
        if role in provided:
            return role
        for fb in FALLBACKS[role]:
            if fb in provided:
                return fb
        if Role.ARROW in provided:
            return Role.ARROW
        return next(iter(provided))

    def render(self, role: Role, size: int = 32, adj: Adjustments | None = None) -> CursorAnim:
        adj = adj or Adjustments()
        size = int(max(8, min(256, size)))
        key = (role, size, adj.key())
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        base = self._render(self.resolve_role(role), size)
        anim = apply_adjustments(base, adj)
        if len(self._cache) > 512:
            self._cache.clear()
        self._cache[key] = anim
        return anim

    def clear_cache(self) -> None:
        self._cache.clear()

    @property
    def animated(self) -> bool:
        return self.meta.animated

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.id!r} {self.name!r}>"


def apply_adjustments(anim: CursorAnim, adj: Adjustments) -> CursorAnim:
    if adj.is_identity():
        return anim
    frames = [imaging.apply_color_adjustments(f, adj) for f in anim.frames]
    hx, hy = anim.hotspot
    if adj.mirror:
        hx = anim.frames[0].width - 1 - hx
    speed = max(0.05, adj.speed)
    delays = [max(10, round(d / speed)) for d in anim.delays] if anim.animated else list(anim.delays)
    return CursorAnim(frames, delays, (hx, hy))


# ============================================================================ sources

@dataclass
class CursorSource:
    """Raw frames for one role as loaded from disk (any size)."""

    frames: list[Image.Image]
    delays: list[int]
    hotspot: tuple[float, float]
    nominal: int  # the size the art was designed for
    pixel_art: bool = False
    svg: bytes | None = None  # if set, frames are rendered from SVG at render time

    def render(self, size: int) -> CursorAnim:
        if self.svg is not None:
            from .qtrender import render_svg
            img = render_svg(self.svg, size)
            f = size / self.nominal
            return CursorAnim([img], [0], (round(self.hotspot[0] * f), round(self.hotspot[1] * f)))
        factor = size / self.nominal
        nearest = self.pixel_art and (factor >= 1 and abs(factor - round(factor)) < 1e-6)
        out = []
        for fr in self.frames:
            fr = _square(fr)
            out.append(_to_canvas(imaging.scale_frame(fr, factor, nearest=nearest), size))
        hx = min(size - 1, round(self.hotspot[0] * factor))
        hy = min(size - 1, round(self.hotspot[1] * factor))
        delays = list(self.delays) if len(out) > 1 else [0]
        return CursorAnim(out, delays, (hx, hy))


def _square(img: Image.Image) -> Image.Image:
    if img.width == img.height:
        return img
    n = max(img.size)
    canvas = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    canvas.paste(img, (0, 0))
    return canvas


def _to_canvas(img: Image.Image, size: int) -> Image.Image:
    if img.size == (size, size):
        return img
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img.crop((0, 0, min(size, img.width), min(size, img.height))), (0, 0))
    return canvas


def _split_strip(img: Image.Image, frames: int) -> list[Image.Image]:
    """Split a sprite strip (horizontal or vertical) into ``frames`` images."""
    if frames <= 1:
        return [img]
    if img.width >= img.height:
        w = img.width // frames
        return [img.crop((i * w, 0, (i + 1) * w, img.height)) for i in range(frames)]
    h = img.height // frames
    return [img.crop((0, i * h, img.width, (i + 1) * h)) for i in range(frames)]


def load_source(data: bytes, ext: str, spec: dict | None = None) -> CursorSource:
    """Decode a cursor/image file.  ``spec`` holds manifest overrides."""
    spec = spec or {}
    ext = ext.lower()
    hotspot = spec.get("hotspot")
    delay = spec.get("delay")
    if ext in VECTOR_EXTS:
        from .qtrender import svg_size
        nominal = int(spec.get("size") or max(svg_size(data)) or 32)
        return CursorSource([], [0], tuple(hotspot or (0, 0)), nominal, svg=data)
    if ext in CURSOR_EXTS or data[:4] == b"RIFF" or data[:4] in (b"\0\0\2\0", b"\0\0\1\0"):
        anim = wincursor.read_any(data)
        frames = [f.image for f in anim.frames]
        hs = tuple(hotspot) if hotspot else anim.frames[0].hotspot
        delays = [int(delay)] * len(frames) if delay else anim.delays_ms
        nominal = max(frames[0].size)
        return CursorSource(frames, delays, hs, nominal, bool(spec.get("pixel_art")))
    if data[:4] == xcursor.MAGIC:
        xc = xcursor.read_xcursor(data)
        want = int(spec.get("size") or 32)
        xf = xc.best(want)
        frames = [f.image for f in xf]
        hs = tuple(hotspot) if hotspot else xf[0].hotspot
        delays = [int(delay)] * len(frames) if delay else [f.delay_ms or 50 for f in xf]
        return CursorSource(frames, delays, hs, max(frames[0].size), bool(spec.get("pixel_art")))
    img = Image.open(io.BytesIO(data))
    frames, delays = [], []
    n = getattr(img, "n_frames", 1)
    if n > 1:
        for fr in ImageSequence.Iterator(img):
            frames.append(fr.convert("RGBA"))
            delays.append(int(delay or fr.info.get("duration") or 100))
    else:
        frames = _split_strip(img.convert("RGBA"), int(spec.get("frames", 1)))
        delays = [int(delay or 50)] * len(frames)
    nominal = int(spec.get("size") or max(frames[0].size))
    return CursorSource(frames, delays, tuple(hotspot or (0, 0)), nominal, bool(spec.get("pixel_art")))


# ============================================================================ FileSkin

class FileSkin(Skin):
    """A skin backed by image files and a ``skin.json`` manifest."""

    def __init__(self, skin_id: str, meta: SkinMeta, sources: dict[Role, CursorSource],
                 path: Path | None = None, manifest: dict | None = None):
        super().__init__(skin_id, meta, path)
        self.sources = sources
        self.manifest = manifest or {}
        main = sources.get(Role.ARROW) or next(iter(sources.values()))
        self.meta.animated = len(main.frames) > 1

    def provided_roles(self) -> set[Role]:
        return set(self.sources)

    def _render(self, role: Role, size: int) -> CursorAnim:
        return self.sources[role].render(size)


def _meta_from_manifest(m: dict, fallback_name: str) -> SkinMeta:
    return SkinMeta(
        name=m.get("name") or fallback_name,
        author=m.get("author") or "Unknown",
        category=m.get("category") or "Custom",
        tags=list(m.get("tags") or []),
        description=m.get("description") or "",
        license=m.get("license") or "",
        version=str(m.get("version") or "1.0"),
    )


class _Reader:
    """Uniform file access for skin folders and ``.mouzeskin`` zip archives."""

    def __init__(self, path: Path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.is_file() else None
        self.prefix = ""
        if self.zip is not None:
            names = self.zip.namelist()
            if "skin.json" not in names:
                for n in names:
                    if n.endswith("/skin.json") and n.count("/") == 1:
                        self.prefix = n[: -len("skin.json")]
                        break

    def read(self, name: str) -> bytes:
        name = name.replace("\\", "/").lstrip("/")
        if ".." in Path(name).parts:
            raise ValueError(f"illegal path in skin: {name}")
        if self.zip is not None:
            return self.zip.read(self.prefix + name)
        return (self.path / name).read_bytes()

    def close(self):
        if self.zip is not None:
            self.zip.close()


def load_skin(path: str | Path, skin_id: str | None = None) -> Skin:
    """Load a skin folder or ``.mouzeskin`` archive."""
    path = Path(path)
    reader = _Reader(path)
    try:
        manifest = json.loads(reader.read("skin.json").decode("utf-8"))
        sid = skin_id or f"user:{path.stem if path.is_file() else path.name}"
        meta = _meta_from_manifest(manifest, path.stem)
        if "generator" in manifest:
            from .builtin.procedural import ProceduralSkin
            return ProceduralSkin.from_recipe(sid, meta, manifest["generator"], path)
        sources: dict[Role, CursorSource] = {}
        for role_name, spec in (manifest.get("cursors") or {}).items():
            try:
                role = Role(role_name)
            except ValueError:
                continue
            if isinstance(spec, str):
                spec = {"file": spec}
            files = spec.get("files")
            if files:
                parts = [load_source(reader.read(f), Path(f).suffix, spec) for f in files]
                frames = [fr for p in parts for fr in p.frames]
                delay = int(spec.get("delay") or 80)
                first = parts[0]
                sources[role] = CursorSource(frames, [delay] * len(frames), first.hotspot,
                                             first.nominal, first.pixel_art)
            else:
                fname = spec["file"]
                sources[role] = load_source(reader.read(fname), Path(fname).suffix, spec)
        if not sources:
            raise ValueError("skin has no cursors")
        return FileSkin(sid, meta, sources, path, manifest)
    finally:
        reader.close()


def save_skin(skin: Skin, dest: str | Path, size: int = 64, adj: Adjustments | None = None,
              roles: list[Role] | None = None) -> Path:
    """Write any skin as a portable FileSkin (folder, or zip if dest ends in .mouzeskin).

    Procedural skins are stored as their recipe *and* as rendered PNG strips so
    that other tools can use them too.
    """
    dest = Path(dest)
    files: dict[str, bytes] = {}
    cursors = {}
    for role in roles or sorted(skin.provided_roles(), key=lambda r: list(Role).index(r)):
        anim = skin.render(role, size, adj)
        fname = f"{role.value}.png"
        if anim.animated:
            strip = Image.new("RGBA", (size * len(anim.frames), size), (0, 0, 0, 0))
            for i, fr in enumerate(anim.frames):
                strip.paste(fr, (i * size, 0))
            img = strip
            spec = {"file": fname, "frames": len(anim.frames), "delay": round(sum(anim.delays) / len(anim.delays)),
                    "hotspot": list(anim.hotspot), "size": size}
        else:
            img = anim.frames[0]
            spec = {"file": fname, "hotspot": list(anim.hotspot), "size": size}
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        files[fname] = buf.getvalue()
        cursors[role.value] = spec
    manifest = {"format": SKIN_FORMAT_VERSION, **skin.meta.to_dict(), "cursors": cursors}
    recipe = getattr(skin, "recipe", None)
    if recipe is not None and (adj is None or adj.is_identity()):
        manifest["generator"] = recipe
    files["skin.json"] = json.dumps(manifest, indent=2).encode("utf-8")
    if dest.suffix.lower() in (SKIN_EXT, ".zip"):
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in files.items():
                zf.writestr(name, data)
    else:
        dest.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (dest / name).write_bytes(data)
    return dest
