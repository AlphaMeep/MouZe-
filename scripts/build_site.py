"""Build the MouZe website: a gallery where visitors can try every skin live.

    python scripts/build_site.py            # writes _site/
    python scripts/build_site.py -o public  # somewhere else

The page itself lives in ``site/``.  This script renders every built-in skin
with MouZe's own CSS exporter (so "try it" on the website uses exactly what
``mouze export -f css`` produces), zips each one as a download for web
developers, and copies the community catalog so it is served from the site
too.  ``.github/workflows/pages.yml`` publishes the result to GitHub Pages.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mouze import __version__  # noqa: E402
from mouze.builtin.catalog import CATEGORIES, SEASON_BY_MONTH, STAFF_PICKS, builtin_skins  # noqa: E402
from mouze.formats.platforms import write_css_pack  # noqa: E402
from mouze.qtrender import ensure_qt_app  # noqa: E402
from mouze.roles import Role  # noqa: E402
from mouze.skin import slugify  # noqa: E402

REPO = "https://github.com/AlphaMeep/MouZe-"
CURSOR_SIZE = 32   # what the page uses as the live cursor
THUMB_SIZE = 96    # card thumbnails, shown at 48 CSS px so they stay sharp on HiDPI screens
MAX_THUMB_FRAMES = 32


def _thumb(skin, dest: Path) -> str:
    """Card image: a PNG, or an animated WebP for animated skins."""
    anim = skin.render(Role.ARROW, THUMB_SIZE)
    if len(anim.frames) > 1:
        step = max(1, len(anim.frames) // MAX_THUMB_FRAMES)
        frames = anim.frames[::step]
        delays = [max(20, sum(anim.delays[i:i + step])) for i in range(0, len(anim.frames), step)][:len(frames)]
        name = dest.with_suffix(".webp")
        frames[0].save(name, save_all=True, append_images=frames[1:], duration=delays, loop=0,
                       quality=85, method=4, lossless=False)
    else:
        name = dest.with_suffix(".png")
        anim.frames[0].save(name, optimize=True)
    return name.name


def _zip_dir(folder: Path, dest: Path, prefix: str) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.iterdir()):
            z.write(f, f"{prefix}/{f.name}")
    dest.write_bytes(buf.getvalue())


def build_skins(out: Path, limit: int | None = None) -> list[dict]:
    skins = builtin_skins()
    if limit:
        # keep every category represented in quick (test) builds
        seen: dict[str, int] = {}
        picked = []
        for s in skins:
            if seen.get(s.meta.category, 0) < limit:
                seen[s.meta.category] = seen.get(s.meta.category, 0) + 1
                picked.append(s)
        skins = picked
    records = []
    for skin in skins:
        slug = slugify(skin.id.split(":", 1)[-1])
        sdir = out / "s" / slug
        write_css_pack(skin, sdir / "web", CURSOR_SIZE)
        _zip_dir(sdir / "web", sdir / f"{slug}-web-cursors.zip", slug)
        thumb = _thumb(skin, sdir / "thumb")
        records.append({
            "id": skin.id, "slug": slug, "name": skin.name, "category": skin.meta.category,
            "tags": list(skin.meta.tags), "description": skin.meta.description, "animated": skin.animated,
            "thumb": f"s/{slug}/{thumb}", "css": f"s/{slug}/web/mouze-cursors.css",
            "zip": f"s/{slug}/{slug}-web-cursors.zip", "pick": skin.id in STAFF_PICKS,
        })
    return records


def build_community(out: Path) -> dict:
    """Mirror ``community/`` so the catalog and its previews are served from the site."""
    src = ROOT / "community"
    if not (src / "index.json").exists():
        return {"name": "", "skins": []}
    shutil.copytree(src, out / "community", dirs_exist_ok=True)
    data = json.loads((src / "index.json").read_text("utf-8"))
    for e in data.get("skins", []):
        for key in ("url", "preview"):
            ref = e.get(key, "")
            if ref and not ref.startswith(("http://", "https://")):
                e[key] = f"community/{ref}"
    return data


def build(out: Path, limit: int | None = None) -> dict:
    ensure_qt_app()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in (ROOT / "site").iterdir():
        if f.is_file() and f.name != "index.html":
            shutil.copy2(f, out / f.name)
    shutil.copy2(ROOT / "mouze" / "assets" / "icon.png", out / "icon.png")
    images = out / "images"
    images.mkdir()
    for name in ("library.png", "effects-demo.png", "studio.png", "discover.png"):
        if (ROOT / "docs" / "images" / name).exists():
            shutil.copy2(ROOT / "docs" / "images" / name, images / name)

    skins = build_skins(out, limit)
    community = build_community(out)
    data = {
        "version": __version__, "repo": REPO, "categories": CATEGORIES,
        "seasons": {str(k): v for k, v in SEASON_BY_MONTH.items()},
        "skins": skins, "community": community,
    }
    page = (ROOT / "site" / "index.html").read_text("utf-8")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = (page.replace("{{DATA}}", payload)
                .replace("{{VERSION}}", html.escape(__version__))
                .replace("{{COUNT}}", str(len(skins)))
                .replace("{{REPO}}", REPO))
    (out / "index.html").write_text(page, "utf-8")
    (out / ".nojekyll").write_text("")
    (out / "skins.json").write_text(json.dumps(skins, indent=1), "utf-8")
    return {"skins": len(skins), "community": len(community.get("skins", []))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", default=str(ROOT / "_site"))
    ap.add_argument("--limit", type=int, default=None, help="only N skins per category (quick preview builds)")
    args = ap.parse_args(argv)
    stats = build(Path(args.output), args.limit)
    size = sum(f.stat().st_size for f in Path(args.output).rglob("*") if f.is_file())
    print(f"Built {stats['skins']} skins + {stats['community']} community skins into {args.output} "
          f"({size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
