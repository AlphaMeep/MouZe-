"""Import and export whole cursor packs.

Import understands:
  * Windows packs: a folder or ``.zip`` with ``.cur``/``.ani`` files, with or
    without an ``install.inf``.
  * Xcursor themes (``index.theme`` + ``cursors/``), folders or ``.tar.gz``.
  * MouZe skins (``skin.json`` folders / ``.mouzeskin``).
  * Loose image files (PNG/GIF/APNG/WebP/AVIF/SVG/CUR/ANI).

Export writes Windows packs (with a right-click-installable ``install.inf``),
Xcursor themes and MouZe skins.
"""

from __future__ import annotations

import configparser
import io
import json
import re
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

from ..imaging import Adjustments
from ..roles import WINDOWS_SCHEME_ORDER, XCURSOR_NAMES, Role, guess_role
from ..skin import SKIN_EXT, SUPPORTED_EXTS, FileSkin, Skin, SkinMeta, load_skin, load_source, save_skin, slugify
from . import wincursor, xcursor

XCURSOR_EXPORT_SIZES = (24, 32, 48, 64, 96)


# =============================================================================== import

class ImportError_(Exception):
    pass


def _extract_archive(path: Path, into: Path) -> Path:
    name = path.name.lower()
    if name.endswith((".zip", SKIN_EXT)):
        with zipfile.ZipFile(path) as zf:
            for member in zf.namelist():
                target = (into / member).resolve()
                if not str(target).startswith(str(into.resolve())):
                    raise ImportError_(f"unsafe path in archive: {member}")
            zf.extractall(into)
    elif name.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar")):
        with tarfile.open(path) as tf:
            tf.extractall(into, filter="data")
    else:
        raise ImportError_(f"unsupported archive: {path.name}")
    entries = [p for p in into.iterdir() if not p.name.startswith(("__MACOSX", "."))]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return into


def _parse_inf(text: str) -> tuple[str | None, dict[Role, str]]:
    """Return (scheme name, role -> file name) from an install.inf."""
    strings: dict[str, str] = {}
    section = None
    scheme_line = None
    scheme_name = None
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip() if not raw.strip().startswith('"') else raw.strip()
        if not line:
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1).strip().lower()
            continue
        if section == "strings" and "=" in line:
            k, v = line.split("=", 1)
            strings[k.strip().lower()] = v.strip().strip('"')
        elif section and "scheme" in section and "control panel\\cursors\\schemes" in line.lower():
            scheme_line = line

    def expand(s: str) -> str:
        return re.sub(r"%([^%]+)%", lambda m: strings.get(m.group(1).lower(), m.group(0)), s)

    mapping: dict[Role, str] = {}
    if scheme_line:
        parts = [(quoted or bare).strip() for quoted, bare in re.findall(r'"([^"]*)"|([^,]+)', scheme_line)]
        # parts: HKCU, Control Panel\Cursors\Schemes, name, [flags], value
        if len(parts) >= 3:
            scheme_name = expand(parts[2])
        value = expand(parts[-1]) if parts else ""
        files = [v.strip() for v in value.split(",")]
        for role, f in zip(WINDOWS_SCHEME_ORDER, files):
            if f:
                mapping[role] = re.split(r"[\\/]", f)[-1]
    if not mapping:
        # Fall back to the variable names commonly used in [Strings]
        for key, val in strings.items():
            role = guess_role(key)
            if role and Path(val).suffix.lower() in (".cur", ".ani"):
                mapping.setdefault(role, val)
    if not scheme_name:
        scheme_name = strings.get("scheme_name") or strings.get("schemename")
    return scheme_name, mapping


def _find_files(root: Path, exts) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts)


def import_windows_pack(root: Path, name: str | None = None) -> tuple[SkinMeta, dict[Role, Path]]:
    files = _find_files(root, {".cur", ".ani"})
    if not files:
        raise ImportError_("no .cur/.ani files found")
    by_name = {f.name.lower(): f for f in files}
    mapping: dict[Role, Path] = {}
    scheme = None
    infs = sorted(root.rglob("*.inf"))
    if infs:
        scheme, inf_map = _parse_inf(infs[0].read_text("utf-8", errors="replace"))
        for role, fname in inf_map.items():
            f = by_name.get(fname.lower())
            if f:
                mapping[role] = f
    for f in files:
        role = guess_role(f.stem)
        if role and role not in mapping:
            mapping[role] = f
    if not mapping:
        mapping[Role.ARROW] = files[0]
    meta = SkinMeta(name=name or scheme or root.name, author="Imported", category="Imported")
    return meta, mapping


def import_xcursor_theme(root: Path) -> tuple[SkinMeta, dict[Role, Path]]:
    cdir = root / "cursors"
    if not cdir.is_dir():
        raise ImportError_("not an Xcursor theme (no cursors/ folder)")
    name = root.name
    index = root / "index.theme"
    if index.exists():
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cp.read_string(index.read_text("utf-8", errors="replace"))
            name = cp.get("Icon Theme", "Name", fallback=name)
        except configparser.Error:
            pass
    mapping: dict[Role, Path] = {}
    for role, names in XCURSOR_NAMES.items():
        for n in names:
            f = cdir / n
            if f.exists():
                mapping[role] = f.resolve()
                break
    if not mapping:
        raise ImportError_("Xcursor theme has no recognised cursors")
    return SkinMeta(name=name, author="Imported", category="Imported"), mapping


def _write_imported(meta: SkinMeta, mapping: dict[Role, Path], dest_root: Path) -> Path:
    """Copy source files into a new skin folder with a manifest."""
    slug = slugify(meta.name)
    dest = dest_root / slug
    i = 2
    while dest.exists():
        dest = dest_root / f"{slug}-{i}"
        i += 1
    dest.mkdir(parents=True)
    cursors = {}
    for role, src in mapping.items():
        data = src.read_bytes()
        ext = src.suffix.lower()
        if data[:4] == xcursor.MAGIC:
            ext = ".xcur"
        fname = f"{role.value}{ext}"
        (dest / fname).write_bytes(data)
        spec = {"file": fname}
        cursors[role.value] = spec
    manifest = {"format": 1, **meta.to_dict(), "cursors": cursors}
    (dest / "skin.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    return dest


def import_path(path: str | Path, skins_dir: Path, name: str | None = None) -> Path:
    """Import anything we understand into ``skins_dir``.  Returns the new skin folder."""
    path = Path(path)
    skins_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = path
        if path.is_file() and path.name.lower().endswith(
                (".zip", SKIN_EXT, ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar")):
            root = _extract_archive(path, Path(tmp))
        if root.is_dir():
            manifest = next(iter(sorted(root.rglob("skin.json"))), None)
            if manifest is not None:
                skin = load_skin(manifest.parent)  # validate
                dest = skins_dir / slugify(name or skin.name)
                i = 2
                base = dest
                while dest.exists():
                    dest = Path(f"{base}-{i}")
                    i += 1
                shutil.copytree(manifest.parent, dest)
                if name:
                    data = json.loads((dest / "skin.json").read_text("utf-8"))
                    data["name"] = name
                    (dest / "skin.json").write_text(json.dumps(data, indent=2), "utf-8")
                return dest
            if (root / "cursors").is_dir() or any(root.rglob("index.theme")):
                theme_root = root if (root / "cursors").is_dir() else next(root.rglob("index.theme")).parent
                meta, mapping = import_xcursor_theme(theme_root)
            elif _find_files(root, {".cur", ".ani"}):
                meta, mapping = import_windows_pack(root, name)
            else:
                images = _find_files(root, SUPPORTED_EXTS)
                if not images:
                    raise ImportError_("nothing importable found")
                mapping = {}
                for f in images:
                    role = guess_role(f.stem) or (Role.ARROW if Role.ARROW not in mapping else None)
                    if role and role not in mapping:
                        mapping[role] = f
                meta = SkinMeta(name=name or root.name, author="Imported", category="Imported")
        else:
            if path.suffix.lower() not in SUPPORTED_EXTS and path.read_bytes()[:4] != xcursor.MAGIC:
                raise ImportError_(f"unsupported file type: {path.suffix}")
            role = guess_role(path.stem) or Role.ARROW
            meta = SkinMeta(name=name or path.stem.replace("_", " ").title(), author="Imported",
                            category="Imported")
            mapping = {role: path}
        if name:
            meta.name = name
        dest = _write_imported(meta, mapping, skins_dir)
    try:
        load_skin(dest)  # make sure it loads
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


# =============================================================================== export

def export_windows_pack(skin: Skin, dest: str | Path, size: int = 48,
                        adj: Adjustments | None = None) -> Path:
    """Write ``.cur``/``.ani`` files plus an ``install.inf`` for every role."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    files: dict[Role, str] = {}
    for role in WINDOWS_SCHEME_ORDER:
        anim = skin.render(role, size, adj)
        fname = write_windows_cursor(anim, dest / role.value, title=skin.name, author=skin.meta.author)
        files[role] = fname.name
    (dest / "install.inf").write_text(_install_inf(skin.name, files), "utf-8")
    (dest / "README.txt").write_text(
        f"{skin.name} - cursor pack exported by MouZe (https://github.com/AlphaMeep/MouZe-)\n\n"
        "To install without MouZe: right-click install.inf and choose Install, then pick\n"
        f"'{skin.name}' under Mouse Properties > Pointers.\n", "utf-8")
    return dest


def write_windows_cursor(anim, base: Path, title: str = "", author: str = "") -> Path:
    if anim.animated:
        ani = wincursor.AnimatedCursor(
            [wincursor.CursorImage(f, anim.hotspot) for f in anim.frames], anim.delays, title, author)
        path = base.with_suffix(".ani")
        path.write_bytes(wincursor.write_ani(ani))
    else:
        path = base.with_suffix(".cur")
        path.write_bytes(wincursor.write_cur(wincursor.CursorImage(anim.frames[0], anim.hotspot)))
    return path


def _install_inf(name: str, files: dict[Role, str]) -> str:
    safe = re.sub(r'[%"\\]', "", name)
    folder = slugify(name)
    keys = {role: f"r_{role.value}" for role in files}
    scheme_value = ",".join(f"%10%\\%CUR_DIR%\\%{keys[r]}%" for r in WINDOWS_SCHEME_ORDER if r in files)
    lines = [
        "; Cursor scheme generated by MouZe",
        "[Version]",
        'signature="$CHICAGO$"',
        "",
        "[DefaultInstall]",
        "CopyFiles = Scheme.Cur",
        "AddReg    = Scheme.Reg",
        "",
        "[DestinationDirs]",
        'Scheme.Cur = 10,"%CUR_DIR%"',
        "",
        "[Scheme.Reg]",
        f'HKCU,"Control Panel\\Cursors\\Schemes","%SCHEME_NAME%",,"{scheme_value}"',
        "",
        "[Scheme.Cur]",
        *[files[r] for r in WINDOWS_SCHEME_ORDER if r in files],
        "",
        "[Strings]",
        f'CUR_DIR       = "Cursors\\{folder}"',
        f'SCHEME_NAME   = "{safe}"',
        *[f'{keys[r]} = "{files[r]}"' for r in WINDOWS_SCHEME_ORDER if r in files],
        "",
    ]
    return "\r\n".join(lines)


def export_xcursor_theme(skin: Skin, dest_root: str | Path, theme_name: str | None = None,
                         sizes=XCURSOR_EXPORT_SIZES, adj: Adjustments | None = None) -> Path:
    """Write an Xcursor theme folder ``dest_root/<theme_name>``."""
    theme_name = theme_name or f"MouZe-{slugify(skin.name)}"
    root = Path(dest_root) / theme_name
    cdir = root / "cursors"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir(parents=True)
    for role, names in XCURSOR_NAMES.items():
        if not names:
            continue
        xc = xcursor.XCursor()
        for s in sizes:
            anim = skin.render(role, s, adj)
            xc.sizes[s] = [xcursor.XFrame(f, anim.hotspot, d if anim.animated else 0)
                           for f, d in zip(anim.frames, anim.delays)]
        (cdir / names[0]).write_bytes(xcursor.write_xcursor(xc))
        for alias in names[1:]:
            link = cdir / alias
            try:
                link.symlink_to(names[0])
            except (OSError, NotImplementedError):
                shutil.copyfile(cdir / names[0], link)
    (root / "index.theme").write_text(
        f"[Icon Theme]\nName={theme_name}\nComment={skin.name} by {skin.meta.author} (MouZe)\n"
        "Inherits=default\n", "utf-8")
    return root


def export_skin(skin: Skin, dest: str | Path, size: int = 64, adj: Adjustments | None = None) -> Path:
    return save_skin(skin, dest, size=size, adj=adj)


def export_preview_png(skin: Skin, dest: str | Path, size: int = 48, adj: Adjustments | None = None) -> Path:
    """A contact sheet of every role - handy for sharing screenshots of a skin."""
    roles = WINDOWS_SCHEME_ORDER
    pad = size // 4
    cols = 6
    rows = (len(roles) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (size + pad) + pad, rows * (size + pad) + pad), (40, 42, 54, 255))
    for i, role in enumerate(roles):
        anim = skin.render(role, size, adj)
        x = pad + (i % cols) * (size + pad)
        y = pad + (i // cols) * (size + pad)
        sheet.alpha_composite(anim.frames[0], (x, y))
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    Path(dest).write_bytes(buf.getvalue())
    return Path(dest)


__all__ = [
    "ImportError_", "import_path", "export_windows_pack", "export_xcursor_theme", "export_skin",
    "export_preview_png", "write_windows_cursor", "FileSkin", "load_source",
]
