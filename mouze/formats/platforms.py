"""Cursor formats from other platforms and apps.

Importers return ``(SkinMeta, {Role: CursorAnim})`` with decoded frames, which
:func:`write_decoded` turns into a normal MouZe skin folder.

Supported here:

* **macOS** - Mousecape ``.cape`` files (import and export).
* **Hyprland** - hyprcursor themes (``manifest.hl`` + ``.hlc`` archives or
  source folders).
* **Linux theme sources** - ``xcursorgen`` config files (``*.in``/``*.cursor``
  + PNGs), as used by most cursor themes on GitHub.
* **Web** - CSS cursor packs (``cursor: url(...) x y, keyword``), including
  data: URIs (import and export).
* **Anything else** - a "smart" folder importer that understands numbered
  frame sequences, sprite sheets and loosely structured JSON/INI metadata.
  Packs from browser extensions, game mods and other cursor apps (including
  Mouse X workshop items, see :mod:`mousex`) go through it.
"""

from __future__ import annotations

import base64
import configparser
import io
import json
import plistlib
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageSequence

from ..imaging import Adjustments
from ..roles import XCURSOR_NAMES, Role, guess_role
from ..skin import SUPPORTED_EXTS, CursorAnim, Skin, SkinMeta, load_source, slugify

RASTER_EXTS = {".png", ".gif", ".webp", ".apng", ".avif", ".bmp", ".jpg", ".jpeg", ".tga", ".tif", ".tiff"}
IGNORED_IMAGE_WORDS = ("preview", "thumb", "banner", "screenshot", "cover", "promo", "showcase")

# Centre-hotspot roles, used when a format gives no hotspot.
CENTRED = {Role.BUSY, Role.PRECISION, Role.MOVE, Role.SIZE_NS, Role.SIZE_EW, Role.SIZE_NWSE,
           Role.SIZE_NESW, Role.UNAVAILABLE}


# ============================================================================== helpers

def _x11_role(name: str) -> Role | None:
    name = name.strip().lower()
    for role, names in XCURSOR_NAMES.items():
        if name in names:
            return role
    return guess_role(name)


def auto_hotspot(img: Image.Image, role: Role | None) -> tuple[int, int]:
    """Best guess at a hotspot: centre for centred roles, else the top-left tip."""
    bbox = img.getchannel("A").getbbox()
    if bbox is None:
        return (0, 0)
    if role in CENTRED:
        return ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
    if role == Role.TEXT:
        return ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
    alpha = img.getchannel("A")
    w, h = img.size
    best, best_score = (bbox[0], bbox[1]), None
    px = alpha.load()
    for y in range(bbox[1], min(bbox[3], bbox[1] + max(4, h // 3))):
        for x in range(bbox[0], min(bbox[2], bbox[0] + max(4, w // 3))):
            if px[x, y] > 96:
                score = x + y * 1.05
                if best_score is None or score < best_score:
                    best, best_score = (x, y), score
    if role == Role.LINK:
        # pointing hands: topmost opaque pixel
        for y in range(bbox[1], bbox[3]):
            row = [x for x in range(bbox[0], bbox[2]) if px[x, y] > 96]
            if row:
                return (row[len(row) // 2], y)
    return best


def anim_from_frames(frames: list[Image.Image], delays: list[int] | None, hotspot, role: Role | None) -> CursorAnim:
    frames = [f.convert("RGBA") for f in frames]
    size = (max(f.width for f in frames), max(f.height for f in frames))
    out = []
    for f in frames:
        if f.size != size:
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            canvas.paste(f, (0, 0))
            f = canvas
        out.append(f)
    delays = list(delays or [])
    if len(out) > 1:
        delays = [int(d) if d else 80 for d in (delays + [delays[-1] if delays else 80] * len(out))[:len(out)]]
    else:
        delays = [0]
    if hotspot is None:
        hotspot = auto_hotspot(out[0], role)
    hx = max(0, min(size[0] - 1, int(round(hotspot[0]))))
    hy = max(0, min(size[1] - 1, int(round(hotspot[1]))))
    return CursorAnim(out, delays, (hx, hy))


def write_decoded(meta: SkinMeta, cursors: dict[Role, CursorAnim], dest_root: Path, extra: dict | None = None) -> Path:
    """Write decoded cursors as a MouZe skin folder (PNG strips + skin.json)."""
    if not cursors:
        raise ValueError("no cursors found")
    slug = slugify(meta.name)
    dest = dest_root / slug
    i = 2
    while dest.exists():
        dest = dest_root / f"{slug}-{i}"
        i += 1
    dest.mkdir(parents=True)
    specs = {}
    for role, anim in cursors.items():
        fname = f"{role.value}.png"
        w, h = anim.frames[0].size
        if anim.animated:
            strip = Image.new("RGBA", (w * len(anim.frames), h), (0, 0, 0, 0))
            for k, fr in enumerate(anim.frames):
                strip.paste(fr, (k * w, 0))
            strip.save(dest / fname, optimize=True)
            spec = {"file": fname, "frames": len(anim.frames), "hotspot": list(anim.hotspot)}
            if len(set(anim.delays)) == 1:
                spec["delay"] = anim.delays[0]
            else:
                spec["delays"] = list(anim.delays)
        else:
            anim.frames[0].save(dest / fname, optimize=True)
            spec = {"file": fname, "hotspot": list(anim.hotspot)}
        spec["size"] = max(w, h)
        specs[role.value] = spec
    manifest = {"format": 1, **meta.to_dict(), "cursors": specs, **(extra or {})}
    (dest / "skin.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    return dest


def _open_image_frames(data: bytes) -> tuple[list[Image.Image], list[int]]:
    img = Image.open(io.BytesIO(data))
    if getattr(img, "n_frames", 1) > 1:
        frames, delays = [], []
        for fr in ImageSequence.Iterator(img):
            frames.append(fr.convert("RGBA"))
            delays.append(int(fr.info.get("duration") or 80))
        return frames, delays
    return [img.convert("RGBA")], [0]


# ============================================================================= Mousecape

# Preferred macOS identifiers per role (first found wins on import; all written on export).
MAC_IDS: dict[Role, list[str]] = {
    Role.ARROW: ["com.apple.coregraphics.Arrow", "com.apple.coregraphics.ArrowCtx", "com.apple.coregraphics.Copy",
                 "com.apple.coregraphics.Alias", "com.apple.cursor.2", "com.apple.cursor.5", "com.apple.cursor.24",
                 "com.apple.cursor.25"],
    Role.TEXT: ["com.apple.coregraphics.IBeam", "com.apple.coregraphics.IBeamXOR", "com.apple.cursor.26"],
    Role.BUSY: ["com.apple.coregraphics.Wait"],
    Role.WORKING: ["com.apple.cursor.4"],
    Role.LINK: ["com.apple.cursor.13", "com.apple.cursor.12"],
    Role.MOVE: ["com.apple.coregraphics.Move", "com.apple.cursor.11", "com.apple.cursor.39"],
    Role.UNAVAILABLE: ["com.apple.cursor.3"],
    Role.PRECISION: ["com.apple.cursor.7", "com.apple.cursor.8", "com.apple.cursor.41", "com.apple.cursor.20",
                     "com.apple.cursor.42", "com.apple.cursor.43"],
    Role.HELP: ["com.apple.cursor.40"],
    Role.SIZE_NS: ["com.apple.cursor.23", "com.apple.cursor.32", "com.apple.cursor.21", "com.apple.cursor.22",
                   "com.apple.cursor.31", "com.apple.cursor.36"],
    Role.SIZE_EW: ["com.apple.cursor.19", "com.apple.cursor.28", "com.apple.cursor.17", "com.apple.cursor.18",
                   "com.apple.cursor.27", "com.apple.cursor.38"],
    Role.SIZE_NWSE: ["com.apple.cursor.34", "com.apple.cursor.33", "com.apple.cursor.35"],
    Role.SIZE_NESW: ["com.apple.cursor.30", "com.apple.cursor.29", "com.apple.cursor.37"],
}


def read_mousecape(data: bytes) -> tuple[SkinMeta, dict[Role, CursorAnim]]:
    cape = plistlib.loads(data)
    cursors_in = cape.get("Cursors") or {}
    out: dict[Role, CursorAnim] = {}
    for role, ids in MAC_IDS.items():
        for cid in ids:
            entry = cursors_in.get(cid)
            if not entry or not entry.get("Representations"):
                continue
            reps = []
            for rep in entry["Representations"]:
                try:
                    reps.append(Image.open(io.BytesIO(bytes(rep))).convert("RGBA"))
                except Exception:  # noqa: BLE001 - skip unreadable representations
                    continue
            if not reps:
                continue
            sheet = max(reps, key=lambda im: im.width)
            n = max(1, int(entry.get("FrameCount", 1)))
            points_w = float(entry.get("PointsWide") or sheet.width)
            scale = sheet.width / points_w if points_w else 1.0
            fh = sheet.height // n
            frames = [sheet.crop((0, i * fh, sheet.width, (i + 1) * fh)) for i in range(n)]
            dur = float(entry.get("FrameDuration") or 0.1)
            hs = (float(entry.get("HotSpotX", 0)) * scale, float(entry.get("HotSpotY", 0)) * scale)
            out[role] = anim_from_frames(frames, [round(dur * 1000)] * n, hs, role)
            break
    if not out:
        raise ValueError("this .cape file has no cursors MouZe understands")
    meta = SkinMeta(name=str(cape.get("CapeName") or "Mousecape import"), author=str(cape.get("Author") or "Unknown"),
                    category="Imported", tags=["macos", "mousecape"], version=str(cape.get("CapeVersion") or "1.0"))
    return meta, out


def write_mousecape(skin: Skin, dest: str | Path, points: int = 32, adj: Adjustments | None = None) -> Path:
    """Export a Mousecape ``.cape`` so the skin can be used on macOS (via Mousecape)."""
    cursors = {}
    for role, ids in MAC_IDS.items():
        reps = []
        anim1 = None
        for scale in (1, 2):
            anim = skin.render(role, points * scale, adj)
            anim1 = anim1 or anim
            w, h = anim.frames[0].size
            sheet = Image.new("RGBA", (w, h * len(anim.frames)), (0, 0, 0, 0))
            for i, fr in enumerate(anim.frames):
                sheet.paste(fr, (0, i * h))
            buf = io.BytesIO()
            sheet.save(buf, "PNG")
            reps.append(buf.getvalue())
        n = len(anim1.frames)
        entry = {
            "FrameCount": n,
            "FrameDuration": (sum(anim1.delays) / n / 1000.0) if anim1.animated else 1.0,
            "HotSpotX": float(anim1.hotspot[0]),
            "HotSpotY": float(anim1.hotspot[1]),
            "PointsWide": float(points),
            "PointsHigh": float(points),
            "Representations": reps,
        }
        for cid in ids:
            cursors[cid] = entry
    cape = {
        "Author": skin.meta.author, "CapeName": skin.name, "CapeVersion": 1.0, "Cloud": False,
        "Cursors": cursors, "HiDPI": True, "Identifier": f"io.github.mouze.{slugify(skin.name)}",
        "MinimumVersion": 2.0, "Version": 2.0,
    }
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(plistlib.dumps(cape, fmt=plistlib.FMT_XML))
    return dest


# ============================================================================ hyprcursor

def _parse_hl(text: str) -> list[tuple[str, str]]:
    """Parse hyprlang/toml-ish ``key = value`` lines (order kept, sections ignored)."""
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("[") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out.append((k.strip().lower(), v.strip().strip("'\"")))
    return out


def _read_hlc(files: dict[str, bytes], shape: str) -> tuple[list[str], CursorAnim] | None:
    meta_name = next((n for n in files if n.lower() in ("meta.hl", "meta.toml")), None)
    if meta_name is None:
        return None
    entries = _parse_hl(files[meta_name].decode("utf-8", "replace"))
    hx = hy = 0.0
    names = [shape]
    sizes: dict[int, list[tuple[str, int]]] = {}
    for k, v in entries:
        if k == "hotspot_x":
            hx = float(v)
        elif k == "hotspot_y":
            hy = float(v)
        elif k == "define_override":
            names += [n.strip() for n in v.split(";") if n.strip()]
        elif k == "define_size":
            parts = [p.strip() for p in v.split(",")]
            if len(parts) >= 2:
                try:
                    size = int(float(parts[0]))
                except ValueError:
                    continue
                delay = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                sizes.setdefault(size, []).append((parts[1], delay))
    if not sizes:
        return None
    raster = [s for s in sizes if s > 0]
    pick = max(raster, key=lambda s: (s <= 128, s)) if raster else 0
    frames, delays = [], []
    for fname, delay in sizes[pick]:
        data = files.get(fname) or files.get(Path(fname).name)
        if data is None:
            continue
        if pick == 0 or fname.lower().endswith(".svg"):
            src = load_source(data, ".svg", {"size": 64})
            frames.append(src.render(64).frames[0])
        else:
            frames.append(Image.open(io.BytesIO(data)).convert("RGBA"))
        delays.append(delay or 50)
    if not frames:
        return None
    w, h = frames[0].size
    return names, anim_from_frames(frames, delays, (hx * w, hy * h), None)


def read_hyprcursor(root: Path) -> tuple[SkinMeta, dict[Role, CursorAnim]]:
    manifest = next((root / n for n in ("manifest.hl", "manifest.toml") if (root / n).exists()), None)
    if manifest is None:
        raise ValueError("not a hyprcursor theme")
    info = dict(_parse_hl(manifest.read_text("utf-8", "replace")))
    cdir = root / (info.get("cursors_directory") or "hyprcursors")
    shapes: list[tuple[str, dict[str, bytes]]] = []
    if cdir.is_dir():
        for entry in sorted(cdir.iterdir()):
            if entry.suffix.lower() == ".hlc" and entry.is_file():
                with zipfile.ZipFile(entry) as zf:
                    shapes.append((entry.stem, {Path(n).name: zf.read(n) for n in zf.namelist() if not n.endswith("/")}))
            elif entry.is_dir():
                shapes.append((entry.name, {f.name: f.read_bytes() for f in entry.iterdir() if f.is_file()}))
    out: dict[Role, CursorAnim] = {}
    for shape, files in shapes:
        res = _read_hlc(files, shape)
        if res is None:
            continue
        names, anim = res
        for n in names:
            role = _x11_role(n)
            if role is not None and role not in out:
                if anim.hotspot == (0, 0) and role in CENTRED:
                    w, h = anim.frames[0].size
                    anim = CursorAnim(anim.frames, anim.delays, (w // 2, h // 2))
                out[role] = anim
                break
    if not out:
        raise ValueError("hyprcursor theme has no recognised cursors")
    meta = SkinMeta(name=info.get("name") or root.name, author="Imported", category="Imported",
                    description=info.get("description", ""), tags=["hyprland"])
    return meta, out


# ============================================================================ xcursorgen

_XCG_LINE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)(?:\s+(\d+))?\s*$")


def find_xcursorgen_configs(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".in", ".cursor", ".conf", ".config") and p.stat().st_size < 65536:
            try:
                lines = [ln for ln in p.read_text("utf-8", "replace").splitlines() if ln.strip()]
            except OSError:
                continue
            if lines and all(_XCG_LINE.match(ln) for ln in lines):
                out.append(p)
    return out


def read_xcursorgen(root: Path, configs: list[Path] | None = None) -> tuple[SkinMeta, dict[Role, CursorAnim]]:
    configs = configs or find_xcursorgen_configs(root)
    by_name = {}
    for img in root.rglob("*.png"):
        by_name.setdefault(img.name, img)
    out: dict[Role, CursorAnim] = {}
    for cfg in configs:
        role = _x11_role(cfg.stem)
        if role is None or role in out:
            continue
        rows = [m.groups() for m in map(_XCG_LINE.match, cfg.read_text("utf-8", "replace").splitlines()) if m]
        sizes = sorted({int(r[0]) for r in rows})
        pick = max([s for s in sizes if s <= 128] or sizes)
        frames, delays, hot = [], [], None
        for size, xh, yh, fname, delay in rows:
            if int(size) != pick:
                continue
            path = (cfg.parent / fname)
            if not path.exists():
                path = by_name.get(Path(fname).name)
            if path is None or not path.exists():
                continue
            frames.append(Image.open(path).convert("RGBA"))
            delays.append(int(delay or 50))
            hot = hot or (int(xh), int(yh))
        if frames:
            out[role] = anim_from_frames(frames, delays, hot, role)
    if not out:
        raise ValueError("no usable xcursorgen configs")
    return SkinMeta(name=root.name, author="Imported", category="Imported", tags=["linux"]), out


# ==================================================================================== CSS

CSS_KEYWORDS = {
    "auto": Role.ARROW, "default": Role.ARROW, "alias": Role.ARROW, "copy": Role.ARROW,
    "context-menu": Role.ARROW, "pointer": Role.LINK, "text": Role.TEXT, "vertical-text": Role.TEXT,
    "wait": Role.BUSY, "progress": Role.WORKING, "crosshair": Role.PRECISION, "cell": Role.PRECISION,
    "zoom-in": Role.PRECISION, "zoom-out": Role.PRECISION, "move": Role.MOVE, "all-scroll": Role.MOVE,
    "grab": Role.MOVE, "grabbing": Role.MOVE, "not-allowed": Role.UNAVAILABLE, "no-drop": Role.UNAVAILABLE,
    "help": Role.HELP, "ns-resize": Role.SIZE_NS, "n-resize": Role.SIZE_NS, "s-resize": Role.SIZE_NS,
    "row-resize": Role.SIZE_NS, "ew-resize": Role.SIZE_EW, "e-resize": Role.SIZE_EW, "w-resize": Role.SIZE_EW,
    "col-resize": Role.SIZE_EW, "nwse-resize": Role.SIZE_NWSE, "nw-resize": Role.SIZE_NWSE,
    "se-resize": Role.SIZE_NWSE, "nesw-resize": Role.SIZE_NESW, "ne-resize": Role.SIZE_NESW,
    "sw-resize": Role.SIZE_NESW,
}
ROLE_CSS = {
    Role.ARROW: ("html, body", "auto"), Role.LINK: ("a, button, [role=button], label, select, summary", "pointer"),
    Role.TEXT: ("input, textarea, [contenteditable]", "text"), Role.BUSY: (".mz-busy", "wait"),
    Role.WORKING: (".mz-working", "progress"), Role.PRECISION: (".mz-precision", "crosshair"),
    Role.MOVE: (".mz-move", "move"), Role.UNAVAILABLE: ("[disabled], .mz-unavailable", "not-allowed"),
    Role.HELP: ("abbr[title], .mz-help", "help"), Role.SIZE_NS: (".mz-size-ns", "ns-resize"),
    Role.SIZE_EW: (".mz-size-ew", "ew-resize"), Role.SIZE_NWSE: (".mz-size-nwse", "nwse-resize"),
    Role.SIZE_NESW: (".mz-size-nesw", "nesw-resize"), Role.HANDWRITING: (".mz-pen", "crosshair"),
    Role.ALTERNATE: (".mz-alternate", "default"),
}
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_CSS_CURSOR = re.compile(r"cursor\s*:\s*((?:url\([^)]*\)|[^;])+)", re.I)
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)\s*(-?\d+(?:\.\d+)?)?\s*(-?\d+(?:\.\d+)?)?", re.I | re.S)


def _css_selector_role(selector: str) -> Role | None:
    s = selector.lower()
    if re.search(r"(^|[\s,>+~])(a|button)\b|:hover|\blink\b|pointer|clickable", s):
        return Role.LINK
    if re.search(r"\b(input|textarea)\b|contenteditable|\btext\b", s):
        return Role.TEXT
    if re.search(r"(^|[\s,])(html|body|\*)\b|^\s*\*\s*$", s):
        return Role.ARROW
    return guess_role(re.sub(r"[^a-z0-9_-]+", "_", s))


def find_css(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*.css")):
        try:
            if "cursor" in p.read_text("utf-8", "replace") and "url(" in p.read_text("utf-8", "replace"):
                out.append(p)
        except OSError:
            continue
    return out


def read_css(css_files: list[Path], root: Path) -> tuple[SkinMeta, dict[Role, CursorAnim]]:
    out: dict[Role, CursorAnim] = {}
    for css in css_files:
        text = re.sub(r"/\*.*?\*/", "", css.read_text("utf-8", "replace"), flags=re.S)
        for selector, body in _CSS_RULE.findall(text):
            for value in _CSS_CURSOR.findall(body):
                keyword = value.replace("!important", "").split(",")[-1].strip().lower()
                role = CSS_KEYWORDS.get(keyword) or _css_selector_role(selector)
                if role is None or role in out:
                    continue
                for _q, url, hx, hy in _CSS_URL.findall(value):
                    data = _css_load(url, css.parent, root)
                    if data is None:
                        continue
                    try:
                        if url.lower().split("?")[0].endswith((".cur", ".ani")):
                            src = load_source(data, Path(url.split("?")[0]).suffix)
                            frames, delays, hs = src.frames, src.delays, src.hotspot
                        elif url.lower().split("?")[0].endswith(".svg") or url.startswith("data:image/svg"):
                            src = load_source(data, ".svg", {"size": 32})
                            frames, delays, hs = [src.render(32).frames[0]], [0], None
                        else:
                            frames, delays = _open_image_frames(data)
                            hs = None
                    except Exception:  # noqa: BLE001 - try the next url() fallback
                        continue
                    if hx and hy:
                        hs = (float(hx), float(hy))
                    out[role] = anim_from_frames(frames, delays, hs, role)
                    break
    if not out:
        raise ValueError("no cursor images found in the CSS")
    return SkinMeta(name=root.name if root.is_dir() else root.stem, author="Imported", category="Imported",
                    tags=["web"]), out


def _css_load(url: str, base: Path, root: Path) -> bytes | None:
    url = url.strip()
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        if ";base64" in header:
            return base64.b64decode(payload)
        from urllib.parse import unquote
        return unquote(payload).encode("utf-8")
    if re.match(r"^[a-z]+://", url, re.I):
        return None  # never fetch remote resources while importing
    rel = url.split("?")[0].split("#")[0].lstrip("/")
    for cand in (base / rel, root / rel, *root.rglob(Path(rel).name)):
        try:
            cand = cand.resolve()
            if cand.is_file() and str(cand).startswith(str(root.resolve())):
                return cand.read_bytes()
        except OSError:
            continue
    return None


def write_css_pack(skin: Skin, dest: str | Path, size: int = 32, adj: Adjustments | None = None) -> Path:
    """Export PNG cursors + a stylesheet for websites (browsers cap cursors at 128 px)."""
    size = max(16, min(128, size))
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    lines = [f"/* {skin.name} by {skin.meta.author} - cursor stylesheet generated by MouZe */", ""]
    for role, (selector, keyword) in ROLE_CSS.items():
        anim = skin.render(role, size, adj)
        fname = f"{role.value}.png"
        anim.frames[0].save(dest / fname, optimize=True)
        hx, hy = anim.hotspot
        lines.append(f"{selector} {{ cursor: url(\"{fname}\") {hx} {hy}, {keyword}; }}")
    (dest / "mouze-cursors.css").write_text("\n".join(lines) + "\n", "utf-8")
    return dest


# ========================================================================= smart folders

def _flatten(obj, prefix="") -> list[tuple[str, object, dict]]:
    """Walk JSON yielding (key, value, containing dict)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()
            out.append((key, v, obj))
            out += _flatten(v, key)
    elif isinstance(obj, list):
        for v in obj:
            out += _flatten(v, prefix)
    return out


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _hotspot_from(d: dict) -> tuple[float, float] | None:
    low = {str(k).lower().replace("-", "_"): v for k, v in d.items()}
    for kx, ky in (("hotspot_x", "hotspot_y"), ("hotspotx", "hotspoty"), ("hotx", "hoty"), ("xhot", "yhot"),
                   ("hot_x", "hot_y"), ("center_x", "center_y"), ("centerx", "centery"), ("pivot_x", "pivot_y"),
                   ("pivotx", "pivoty"), ("anchor_x", "anchor_y"), ("anchorx", "anchory"), ("offset_x", "offset_y"),
                   ("offsetx", "offsety"), ("click_x", "click_y")):
        if kx in low and ky in low and _num(low[kx]) is not None and _num(low[ky]) is not None:
            return (_num(low[kx]), _num(low[ky]))
    for key in ("hotspot", "hot_spot", "hot", "center", "centre", "pivot", "anchor", "clickpoint", "click_point",
                "offset", "origin", "tip"):
        v = low.get(key)
        if isinstance(v, (list, tuple)) and len(v) >= 2 and _num(v[0]) is not None and _num(v[1]) is not None:
            return (_num(v[0]), _num(v[1]))
        if isinstance(v, dict):
            inner = {str(k).lower(): val for k, val in v.items()}
            if _num(inner.get("x")) is not None and _num(inner.get("y")) is not None:
                return (_num(inner["x"]), _num(inner["y"]))
        if isinstance(v, str) and re.match(r"^\s*-?\d+(\.\d+)?\s*[, ]\s*-?\d+(\.\d+)?\s*$", v):
            a, b = re.split(r"[, ]+", v.strip())[:2]
            return (float(a), float(b))
    return None


def _delay_from(d: dict) -> int | None:
    low = {str(k).lower().replace("-", "_"): v for k, v in d.items()}
    for key in ("delay", "frame_delay", "framedelay", "frame_time", "frametime", "interval", "duration",
                "frame_duration", "frameduration", "speed_ms"):
        n = _num(low.get(key))
        if n is not None and n > 0:
            return int(n * 1000) if n < 5 else int(n)
    for key in ("fps", "framerate", "frame_rate", "frames_per_second"):
        n = _num(low.get(key))
        if n:
            return max(10, int(1000 / n))
    return None


def _read_metadata(root: Path) -> tuple[dict, list[dict]]:
    """Collect loose metadata: ({name, author, hotspot, delay, size}, [dicts mentioning files])."""
    info: dict = {}
    file_dicts: list[dict] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        suffix = p.suffix.lower()
        data = None
        if suffix == ".json":
            try:
                data = json.loads(p.read_text("utf-8-sig", "replace"))
            except ValueError:
                continue
        elif suffix in (".ini", ".cfg", ".txt", ".conf", ".properties", ".vdf", ".yaml", ".yml", ".toml"):
            text = p.read_text("utf-8", "replace")
            if suffix == ".ini":
                cp = configparser.ConfigParser(interpolation=None, strict=False)
                try:
                    cp.read_string(text)
                    data = {s: dict(cp[s]) for s in cp.sections()}
                except configparser.Error:
                    data = None
            if data is None:
                data = {}
                for m in re.finditer(r'^\s*"?([A-Za-z_][\w .-]*)"?\s*[:=]?\s+"?([^"\n]+?)"?\s*$', text, re.M):
                    data[m.group(1).strip()] = m.group(2).strip()
        if data is None:
            continue
        for key, value, holder in _flatten(data):
            if key in ("name", "title", "skinname", "skin_name", "display_name", "displayname") and isinstance(value, str):
                info.setdefault("name", value)
            elif key in ("author", "creator", "artist", "made_by", "madeby") and isinstance(value, str):
                info.setdefault("author", value)
            elif key in ("description", "desc") and isinstance(value, str):
                info.setdefault("description", value)
            elif key in ("size", "scale", "cursor_size", "cursorsize") and _num(value):
                info.setdefault(key, _num(value))
            if isinstance(value, str) and Path(value).suffix.lower() in SUPPORTED_EXTS:
                file_dicts.append(holder)
        if isinstance(data, dict):
            hs = _hotspot_from(data)
            if hs is not None:
                info.setdefault("hotspot", hs)
            dl = _delay_from(data)
            if dl is not None:
                info.setdefault("delay", dl)
            for _k, v, _h in _flatten(data):
                if isinstance(v, dict):
                    if "hotspot" not in info:
                        hs = _hotspot_from(v)
                        if hs is not None:
                            info["hotspot"] = hs
                    if "delay" not in info:
                        dl = _delay_from(v)
                        if dl is not None:
                            info["delay"] = dl
    return info, file_dicts


_SEQ = re.compile(r"^(.*?)[\s_.-]*(\d+)$")


def _group_images(images: list[Path]) -> list[tuple[str, list[Path]]]:
    """Group numbered frames (``walk_01.png``, ``frames/3.png``) into sequences."""
    groups: dict[tuple[Path, str], list[tuple[int, Path]]] = {}
    for img in images:
        m = _SEQ.match(img.stem)
        if m:
            base = m.group(1).strip(" _-.") or img.parent.name
            groups.setdefault((img.parent, base.lower()), []).append((int(m.group(2)), img))
        else:
            groups.setdefault((img.parent, img.stem.lower() + "\0single"), []).append((0, img))
    out = []
    for (parent, base), items in groups.items():
        items.sort()
        name = base.replace("\0single", "")
        if name == parent.name.lower() or not name:
            name = parent.name
        if len(items) > 1 and "\0single" not in base:
            out.append((name, [p for _, p in items]))
        else:
            for _, p in items:
                out.append((p.stem if "\0single" in base else name, [p]))
    return out


def read_smart_folder(root: Path, name: str | None = None) -> tuple[SkinMeta, dict[Role, CursorAnim]]:
    """Best-effort import of an arbitrary folder of cursor images."""
    images = [p for p in sorted(root.rglob("*"))
              if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
              and not any(w in p.stem.lower() for w in IGNORED_IMAGE_WORDS)]
    if not images:
        raise ValueError("no cursor images found")
    info, file_dicts = _read_metadata(root)

    def spec_for(path: Path) -> dict:
        for d in file_dicts:
            if any(isinstance(v, str) and Path(v).name.lower() == path.name.lower() for v in d.values()):
                return d
        return {}

    out: dict[Role, CursorAnim] = {}
    pending = []
    for gname, files in _group_images(images):
        role = guess_role(gname) or guess_role(files[0].parent.name)
        pending.append((role, gname, files))
    # unknown groups: the first becomes the arrow if nothing else claims it
    for role, _gname, files in sorted(pending, key=lambda t: t[0] is None):
        if role is None:
            if Role.ARROW in out:
                continue
            role = Role.ARROW
        if role in out:
            continue
        frames, delays = [], []
        for f in files:
            data = f.read_bytes()
            if f.suffix.lower() in (".cur", ".ani", ".ico", ".svg"):
                src = load_source(data, f.suffix, {"size": 64} if f.suffix.lower() == ".svg" else None)
                if src.svg is not None:
                    frames.append(src.render(64).frames[0])
                    delays.append(0)
                    file_hot = None
                else:
                    frames += src.frames
                    delays += src.delays
                    file_hot = src.hotspot
            else:
                fr, dl = _open_image_frames(data)
                frames += fr
                delays += dl
                file_hot = None
        meta_d = spec_for(files[0])
        hs = _hotspot_from(meta_d) if meta_d else None
        if hs is None and len(out) == 0 and role == Role.ARROW:
            hs = info.get("hotspot")
        if hs is None:
            hs = file_hot
        delay = (_delay_from(meta_d) if meta_d else None) or info.get("delay")
        if delay and len(frames) > 1:
            delays = [delay] * len(frames)
        if hs is not None and 0 <= hs[0] <= 1 and 0 <= hs[1] <= 1 and isinstance(hs[0], float) \
                and (hs[0] % 1 or hs[1] % 1):
            hs = (hs[0] * frames[0].width, hs[1] * frames[0].height)
        out[role] = anim_from_frames(frames, delays, hs, role)
    meta = SkinMeta(name=name or info.get("name") or root.name, author=info.get("author") or "Imported",
                    category="Imported", description=info.get("description", ""))
    return meta, out
