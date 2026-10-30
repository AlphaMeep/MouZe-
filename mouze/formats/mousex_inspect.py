"""Describe how Mouse X stores skins on this computer, to improve MouZe's importer.

Mouse X has not published its skin format, so the importer in ``mousex.py``
has to guess.  This module writes a Markdown *format report* about what is
actually on disk: the Mouse X install (which engine it uses, where settings
live), its settings and app-data files, and every downloaded Workshop item.
For each file it records the layout and format details that matter for an
importer (image size, frame count and timing, cursor hotspots, the keys and
numbers in metadata files, magic bytes of unknown files) plus what MouZe's
importer currently makes of it.

The report never contains artwork, program code or full text files, and your
home folder and user name are replaced in paths.  Run it with
``mouze import-mousex --report`` or the *Save format report* button in the
Mouse X import dialog.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import math
import os
import platform
import re
import sys
from collections import Counter
from pathlib import Path

from .. import __version__
from . import mousex

MAX_ITEMS = 25          # Workshop items described in detail
MAX_FILES = 150         # files listed per folder
MAX_TEXT = 256 * 1024   # larger text/metadata files are only listed
NAME_RE = re.compile(r"mouse[\s_-]?x", re.I)
TEXT_EXTS = {".json", ".ini", ".cfg", ".conf", ".txt", ".xml", ".vdf", ".acf", ".yaml", ".yml", ".toml", ".meta"}
MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "PNG image"), (b"GIF8", "GIF image"), (b"RIFF", "RIFF container"),
    (b"\xff\xd8\xff", "JPEG image"), (b"PK\x03\x04", "ZIP archive"), (b"\x1f\x8b", "gzip"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"), (b"UnityFS", "Unity asset bundle"), (b"MZ", "Windows executable"),
    (b"\x00\x00\x02\x00", "CUR cursor"), (b"\x00\x00\x01\x00", "ICO icon"), (b"BM", "BMP image"),
    (b"GDPC", "Godot pack"), (b"{", "JSON-like text"), (b"<", "XML/SVG-like text"), (b"\x28\xb5\x2f\xfd", "zstd"),
    (b"\x04\x22\x4d\x18", "LZ4 frame"), (b"SQLite format 3", "SQLite database"),
]
ENGINE_MARKERS = [
    ("UnityPlayer.dll", "Unity (settings usually in the registry under HKCU\\Software\\<company>\\<product>, "
                        "or in AppData\\LocalLow)"),
    ("GameAssembly.dll", "Unity IL2CPP build"),
    ("resources/app.asar", "Electron (an app.asar archive holds the JavaScript app)"),
    ("Qt6Core.dll", "Qt 6"), ("Qt5Core.dll", "Qt 5"),
    ("libcef.dll", "Chromium Embedded Framework"),
    ("WebView2Loader.dll", "WebView2 (web UI hosted by a native app)"),
    ("steam_api64.dll", "Steamworks API (Workshop/Steam integration)"),
]


def _redact(text: str) -> str:
    home = str(Path.home())
    if home and home not in ("/", "\\"):
        text = text.replace(home, "~").replace(home.replace("\\", "/"), "~")
    for var in ("USERNAME", "USER"):
        name = os.environ.get(var)
        if name and len(name) > 2:
            text = re.sub(re.escape(name), "<user>", text, flags=re.I)
    return text


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    return -sum(c / len(data) * math.log2(c / len(data)) for c in counts.values())


def _magic(head: bytes) -> str:
    for sig, name in MAGIC:
        if head.startswith(sig):
            if sig == b"RIFF" and len(head) >= 12:
                return f"RIFF/{head[8:12].decode('latin-1')}" + (" (ANI cursor)" if head[8:12] == b"ACON" else "")
            return name
    return ""


def _scalar(v) -> str:
    if isinstance(v, str):
        s = _redact(v)
        return json.dumps(s if len(s) <= 60 else s[:57] + "...")
    return json.dumps(v)


def _schema(obj, indent: int = 0, depth: int = 0, budget: list[int] | None = None) -> list[str]:
    """Keys, value types and short values of parsed metadata, as an indented outline."""
    budget = budget if budget is not None else [120]
    pad = "  " * indent
    lines: list[str] = []
    if depth > 5:
        return [f"{pad}..."]
    if isinstance(obj, dict):
        for k, v in obj.items():
            if budget[0] <= 0:
                lines.append(f"{pad}... ({len(obj)} keys in total)")
                break
            budget[0] -= 1
            if isinstance(v, (dict, list)):
                kind = f"object ({len(v)} keys)" if isinstance(v, dict) else f"list[{len(v)}]"
                lines.append(f"{pad}- `{k}`: {kind}")
                lines += _schema(v, indent + 1, depth + 1, budget)
            else:
                lines.append(f"{pad}- `{k}`: {type(v).__name__} = {_scalar(v)}")
    elif isinstance(obj, list):
        if obj and all(not isinstance(x, (dict, list)) for x in obj):
            shown = ", ".join(_scalar(x) for x in obj[:8])
            lines.append(f"{pad}- [{shown}{', ...' if len(obj) > 8 else ''}]")
        elif obj:
            lines.append(f"{pad}- item 0 of {len(obj)}:")
            lines += _schema(obj[0], indent + 1, depth + 1, budget)
    else:
        lines.append(f"{pad}- {type(obj).__name__} = {_scalar(obj)}")
    return lines


def _ini_schema(text: str) -> list[str]:
    lines, n = [], 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        n += 1
        if n > 80:
            lines.append("  - ...")
            break
        if line.startswith("[") and line.endswith("]"):
            lines.append(f"  - section `{line}`")
        elif "=" in line or ":" in line:
            k, _, v = line.partition("=" if "=" in line else ":")
            lines.append(f"    - `{k.strip()}` = {_scalar(v.strip())}")
    return lines


def _xml_schema(text: str) -> list[str]:
    tags = Counter(re.findall(r"<([A-Za-z_][\w.:-]*)", text))
    attrs = Counter(re.findall(r"\s([A-Za-z_][\w.:-]*)=\"", text))
    out = ["  - elements: " + ", ".join(f"`{t}`×{n}" for t, n in tags.most_common(25))]
    if attrs:
        out.append("  - attributes: " + ", ".join(f"`{a}`" for a, _ in attrs.most_common(25)))
    return out


def _describe_image(data: bytes) -> str:
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        parts = [f"{im.format} {im.width}×{im.height} {im.mode}"]
        n = getattr(im, "n_frames", 1)
        if n > 1:
            durations = []
            for i in range(min(n, 200)):
                im.seek(i)
                durations.append(im.info.get("duration", 0))
            common = Counter(durations).most_common(3)
            parts.append(f"{n} frames, durations ms: " + ", ".join(f"{d}×{c}" for d, c in common))
        for key in ("loop", "dpi", "transparency"):
            if key in im.info:
                parts.append(f"{key}={im.info[key]}")
        text_keys = [k for k in im.info if isinstance(im.info[k], str) and k not in ("icc_profile",)]
        if text_keys:
            parts.append("text chunks: " + ", ".join(f"{k}={_scalar(im.info[k])}" for k in text_keys[:6]))
        if im.width and im.height and im.width != im.height and (im.width % im.height == 0 or
                                                                 im.height % im.width == 0):
            ratio = max(im.width, im.height) // min(im.width, im.height)
            parts.append(f"possible {ratio}-frame strip")
    return ", ".join(parts)


def _describe_cursor(data: bytes) -> str:
    from .wincursor import read_ani, read_cur_all
    if data[:4] == b"RIFF":
        ani = read_ani(data)
        f0 = ani.frames[0]
        delays = Counter(ani.delays_ms).most_common(3)
        return (f"ANI {len(ani.frames)} frames, {f0.image.width}×{f0.image.height}, hotspot {f0.hotspot}, "
                f"delays ms: " + ", ".join(f"{d}×{c}" for d, c in delays))
    imgs = read_cur_all(data)
    return "CUR/ICO " + ", ".join(f"{c.image.width}×{c.image.height} hotspot {c.hotspot}" for c in imgs[:6])


def describe_file(path: Path) -> list[str]:
    """One summary line, plus an outline for metadata files."""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            head = f.read(64)
    except OSError as exc:
        return [f"unreadable ({exc.__class__.__name__})"]
    ext = path.suffix.lower()
    magic = _magic(head)
    detail: list[str] = []
    summary = magic or (ext[1:].upper() + " file" if ext else "file")
    try:
        if ext in (".cur", ".ani", ".ico") or magic.startswith(("CUR", "ICO")) or "ANI" in magic:
            summary = _describe_cursor(path.read_bytes())
        elif ext in (".png", ".gif", ".jpg", ".jpeg", ".webp", ".apng", ".bmp", ".tif", ".tiff", ".avif") or \
                magic.endswith("image"):
            summary = _describe_image(path.read_bytes())
        elif ext == ".svg":
            text = path.read_text("utf-8", "replace")[:4000]
            vb = re.search(r'viewBox="([^"]+)"', text)
            summary = f"SVG{' viewBox ' + vb[1] if vb else ''}"
        elif (ext in TEXT_EXTS or magic in ("JSON-like text", "XML/SVG-like text")) and size <= MAX_TEXT:
            text = path.read_text("utf-8-sig", "replace")
            parsed = None
            if ext == ".json" or text.lstrip()[:1] in ("{", "["):
                try:
                    parsed = json.loads(text)
                except ValueError:
                    pass
            if parsed is not None:
                summary, detail = "JSON", _schema(parsed, 1)
            elif ext == ".json":
                summary = "JSON-like text (does not parse)"
            elif ext in (".xml",) or text.lstrip().startswith("<"):
                summary, detail = "XML", _xml_schema(text)
            elif ext in (".ini", ".cfg", ".conf", ".txt", ".meta", ".toml", ".yaml", ".yml") or "=" in text:
                summary, detail = f"text ({len(text.splitlines())} lines)", _ini_schema(text)
            else:
                summary = f"text ({len(text.splitlines())} lines)"
        elif not magic:
            with path.open("rb") as f:
                sample = f.read(4096)
            printable = re.sub(rb"[^\x20-\x7e]", b".", head[:16]).decode()
            summary = (f"unknown binary, first bytes {head[:16].hex(' ')} `{printable}`, "
                       f"entropy {_entropy(sample):.2f} bits/byte"
                       + (" (looks compressed or encrypted)" if _entropy(sample) > 7.5 else ""))
    except Exception as exc:  # noqa: BLE001 - a report should never crash on one odd file
        summary += f" (could not decode: {exc.__class__.__name__}: {_redact(str(exc))[:80]})"
    return [f"{_size(size)}, {summary}", *detail]


def describe_tree(root: Path, limit: int = MAX_FILES) -> list[str]:
    files = [p for p in sorted(root.rglob("*")) if p.is_file()]
    lines = []
    for p in files[:limit]:
        desc = describe_file(p)
        lines.append(f"- `{p.relative_to(root).as_posix()}`: {desc[0]}")
        lines += ["  " + d for d in desc[1:]]
    if len(files) > limit:
        exts = Counter(p.suffix.lower() or "(none)" for p in files[limit:])
        lines.append(f"- ... {len(files) - limit} more files: " + ", ".join(f"{e}×{n}" for e, n in exts.most_common()))
    if not files:
        lines.append("- (empty folder)")
    return lines


# ------------------------------------------------------------------------- locations

def install_dirs() -> list[Path]:
    """Mouse X install folders, from Steam's app manifest or by folder name."""
    out: list[Path] = []
    for lib in mousex.library_folders():
        apps = lib / "steamapps"
        acf = apps / f"appmanifest_{mousex.MOUSE_X_APPID}.acf"
        if acf.exists():
            m = re.search(r'"installdir"\s+"([^"]+)"', acf.read_text("utf-8", "replace"))
            if m and (apps / "common" / m[1]).is_dir():
                out.append(apps / "common" / m[1])
        common = apps / "common"
        if common.is_dir():
            out += [d for d in common.iterdir() if d.is_dir() and NAME_RE.search(d.name)]
    return list(dict.fromkeys(p.resolve() for p in out))


def data_dirs() -> list[Path]:
    """Settings and app-data folders that look like Mouse X's."""
    bases: list[Path] = []
    for var in ("APPDATA", "LOCALAPPDATA"):
        if os.environ.get(var):
            bases.append(Path(os.environ[var]))
    if os.environ.get("LOCALAPPDATA"):
        bases.append(Path(os.environ["LOCALAPPDATA"]).parent / "LocalLow")
    home = Path.home()
    bases += [home / "Documents", home / ".config", home / ".local" / "share"]
    # Proton prefix on Linux / Steam Deck
    for lib in mousex.library_folders():
        user = lib / "steamapps" / "compatdata" / str(mousex.MOUSE_X_APPID) / "pfx" / "drive_c" / "users" / "steamuser"
        bases += [user / "AppData" / "Roaming", user / "AppData" / "Local", user / "AppData" / "LocalLow",
                  user / "Documents"]
    found: list[Path] = []
    for base in bases:
        if not base.is_dir():
            continue
        try:
            level1 = [d for d in base.iterdir() if d.is_dir()]
        except OSError:
            continue
        for d in level1:
            if NAME_RE.search(d.name):
                found.append(d)
                continue
            try:
                found += [s for s in d.iterdir() if s.is_dir() and NAME_RE.search(s.name)]
            except OSError:
                continue
    return list(dict.fromkeys(p.resolve() for p in found))


def registry_lines() -> list[str]:  # pragma: no cover - Windows only
    """Value names and types under HKCU\\Software keys that look like Mouse X's."""
    if sys.platform != "win32":
        return []
    import winreg
    out: list[str] = []
    types = {getattr(winreg, n): n for n in dir(winreg) if n.startswith("REG_")}

    def dump(key, path: str, depth: int):
        out.append(f"- `HKCU\\{path}`")
        i = 0
        while i < 80:
            try:
                name, value, kind = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if isinstance(value, bytes):
                text = value.rstrip(b"\0")
                shown = (_scalar(text.decode("utf-8", "replace")) if text and all(32 <= b < 127 for b in text)
                         else f"{len(value)} bytes")
            else:
                shown = _scalar(value)
            out.append(f"  - `{name}` ({types.get(kind, kind)}) = {shown}")
        if depth < 2:
            j = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, j)
                except OSError:
                    break
                j += 1
                with winreg.OpenKey(key, sub) as k2:
                    dump(k2, f"{path}\\{sub}", depth + 1)

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software") as sw:
            j = 0
            while True:
                try:
                    company = winreg.EnumKey(sw, j)
                except OSError:
                    break
                j += 1
                try:
                    with winreg.OpenKey(sw, company) as ck:
                        if NAME_RE.search(company):
                            dump(ck, f"Software\\{company}", 1)
                            continue
                        k = 0
                        while True:
                            try:
                                product = winreg.EnumKey(ck, k)
                            except OSError:
                                break
                            k += 1
                            if NAME_RE.search(product):
                                with winreg.OpenKey(ck, product) as pk:
                                    dump(pk, f"Software\\{company}\\{product}", 1)
                except OSError:
                    continue
    except OSError:
        pass
    return out


def workshop_dirs(appids=(mousex.MOUSE_X_APPID,)) -> list[tuple[int, Path]]:
    """Every downloaded Workshop item folder, including ones the importer skips."""
    out = []
    for lib in mousex.library_folders():
        for appid in appids:
            content = lib / "steamapps" / "workshop" / "content" / str(appid)
            if content.is_dir():
                out += [(appid, d) for d in sorted(content.iterdir()) if d.is_dir()]
    return out


def _importer_view(folder: Path) -> list[str]:
    """What MouZe's importer currently makes of a folder."""
    from .packs import detect_kind
    from .platforms import read_smart_folder
    try:
        kind = detect_kind(folder)
    except Exception as exc:  # noqa: BLE001
        return [f"- detection failed: {exc.__class__.__name__}"]
    lines = [f"- detected as: **{kind}**", f"- skipped by the importer: {'no' if mousex._has_cursor_files(folder) else 'yes'}"]
    if kind != "images":
        return lines
    try:
        _meta, cursors = read_smart_folder(folder)
    except Exception as exc:  # noqa: BLE001
        lines.append(f"- would fail: {_redact(str(exc))[:120]}")
        return lines
    for role, anim in cursors.items():
        w, h = anim.frames[0].size
        lines.append(f"- {role.value}: {len(anim.frames)} frame(s) {w}×{h}, hotspot {tuple(anim.hotspot)}")
    return lines


# ------------------------------------------------------------------------- report

def build_report(extra_dirs: list[Path] | None = None, appids=(mousex.MOUSE_X_APPID,)) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# Mouse X format report",
        "",
        f"Made by MouZe {__version__} on {platform.system()} {platform.release()} ({platform.machine()}), "
        f"Python {platform.python_version()}, {now}.",
        "",
        "This report describes how Mouse X stores skins on this computer so MouZe's importer can read them "
        "correctly. It lists file layouts and format details only: no artwork, program code or full text files. "
        "Your home folder and user name are replaced with `~` and `<user>`.",
        "",
        f"Steam libraries found: {len(mousex.library_folders())}",
        "",
        "## Mouse X install",
        "",
    ]
    installs = install_dirs()
    if not installs:
        out.append("Not found in any Steam library.")
    for inst in installs:
        files = [p for p in inst.rglob("*") if p.is_file()]
        rel = {p.relative_to(inst).as_posix() for p in files}
        names = {Path(r).name for r in rel}
        out += [f"### `{_redact(str(inst))}`", "",
                f"{len(files)} files, {_size(sum(p.stat().st_size for p in files))}.", ""]
        engines = [desc for marker, desc in ENGINE_MARKERS if marker in rel or marker in names]
        if any(r.endswith("_Data/globalgamemanagers") or r.endswith("_Data/data.unity3d") for r in rel):
            engines.append("Unity data folder present")
        if any(r.endswith(".pck") for r in rel):
            engines.append("Godot .pck present")
        if any(r.endswith(".runtimeconfig.json") for r in rel):
            engines.append(".NET runtime config present")
        out.append("Engine hints: " + ("; ".join(engines) if engines else "none recognised"))
        out += ["", "File types: " + ", ".join(f"`{e}`×{n}" for e, n in
                                               Counter(p.suffix.lower() or "(none)" for p in files).most_common(30)),
                "", "Top-level entries:", ""]
        for p in sorted(inst.iterdir())[:60]:
            kind = "folder" if p.is_dir() else _size(p.stat().st_size)
            out.append(f"- `{p.name}` ({kind})")
        skinish = [p for p in files if re.search(r"skin|cursor|workshop|preset|default", p.as_posix(), re.I)
                   and p.suffix.lower() in TEXT_EXTS | {".png", ".gif", ".cur", ".ani", ".svg", ".avif", ""}]
        if skinish:
            out += ["", "Files that look skin-related:", ""]
            for p in skinish[:40]:
                out.append(f"- `{p.relative_to(inst).as_posix()}`: {describe_file(p)[0]}")
        out.append("")

    out += ["## Settings and app data", ""]
    dirs = data_dirs()
    reg = registry_lines()
    if not dirs and not reg:
        out.append("No Mouse X settings folders or registry keys found.")
    for d in dirs:
        out += [f"### `{_redact(str(d))}`", "", *describe_tree(d, 100), ""]
    if reg:
        out += ["### Registry", "", *reg, ""]

    out += ["## Workshop items", ""]
    items = workshop_dirs(appids) + [(mousex.MOUSE_X_APPID, d) for e in extra_dirs or [] if e.is_dir()
                                     for d in sorted(e.iterdir()) if d.is_dir()]
    if not items:
        out.append("No downloaded Workshop items found.")
    else:
        all_exts = Counter(p.suffix.lower() or "(none)" for _, d in items for p in d.rglob("*") if p.is_file())
        out += [f"{len(items)} item folder(s). File types across all items: "
                + ", ".join(f"`{e}`×{n}" for e, n in all_exts.most_common(20)), ""]
    for appid, d in items[:MAX_ITEMS]:
        title, author, _preview = mousex._local_meta(d)
        out += [f"### {mousex.KNOWN_APPS.get(appid, appid)} item `{d.name}`" + (f": {_scalar(title)}" if title else ""),
                "", *describe_tree(d), "", "What MouZe's importer makes of it:", "", *_importer_view(d), ""]
    if len(items) > MAX_ITEMS:
        out.append(f"... and {len(items) - MAX_ITEMS} more item(s) not described.")
    return _redact("\n".join(out)) + "\n"


def default_report_path() -> Path:
    desktop = Path.home() / "Desktop"
    return (desktop if desktop.is_dir() else Path.cwd()) / "mousex-format-report.md"


def write_report(dest: str | Path | None = None, extra_dirs: list[Path] | None = None, appids=None) -> Path:
    dest = Path(dest) if dest else default_report_path()
    dest.write_text(build_report(extra_dirs, appids or (mousex.MOUSE_X_APPID,)), "utf-8")
    return dest


__all__ = ["build_report", "write_report", "describe_file", "describe_tree", "default_report_path"]
