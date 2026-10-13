"""Command line interface.  ``mouze`` with no arguments starts the GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def _find_skin(library, query: str):
    skin = library.get(query) or library.get(f"builtin:{query}") or library.get(f"user:{query}")
    if skin:
        return skin
    q = query.lower()
    exact = [s for s in library if s.name.lower() == q]
    if exact:
        return exact[0]
    partial = library.search(query)
    if len(partial) == 1:
        return partial[0]
    if partial:
        names = ", ".join(f"{s.name} ({s.id})" for s in partial[:8])
        raise SystemExit(f"'{query}' is ambiguous: {names}{' ...' if len(partial) > 8 else ''}")
    raise SystemExit(f"no skin matches '{query}' (try: mouze list)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mouze", description="MouZe - open-source custom cursors and cursor effects")
    p.add_argument("--version", action="version", version=f"MouZe {__version__}")
    p.add_argument("--minimized", action="store_true", help="start the GUI in the system tray")
    sub = p.add_subparsers(dest="cmd")

    ls = sub.add_parser("list", help="list skins")
    ls.add_argument("-c", "--category")
    ls.add_argument("-s", "--search", default="")
    ls.add_argument("--animated", action="store_true", help="only animated skins")

    sub.add_parser("categories", help="list categories")

    info = sub.add_parser("info", help="show details for a skin")
    info.add_argument("skin")

    ap = sub.add_parser("apply", help="set a skin as the system cursor")
    ap.add_argument("skin")
    ap.add_argument("--size", type=int, default=None)

    rs = sub.add_parser("restore", help="restore the cursors you had before MouZe")
    rs.add_argument("--default", action="store_true", help="restore the OS default cursors instead")

    ex = sub.add_parser("export", help="export a skin")
    ex.add_argument("skin")
    ex.add_argument("-f", "--format", choices=["windows", "xcursor", "skin", "preview"], default="windows")
    ex.add_argument("-o", "--output", required=True)
    ex.add_argument("--size", type=int, default=48)

    im = sub.add_parser("import", help="import a cursor pack, theme, skin or image")
    im.add_argument("path")
    im.add_argument("--name")

    mx = sub.add_parser("import-mousex", help="import your downloaded Mouse X (Steam Workshop) skins")
    mx.add_argument("--list", action="store_true", help="only list what was found")
    mx.add_argument("--online", action="store_true", help="look up item titles with the Steam Web API")
    mx.add_argument("--folder", action="append", default=[], help="extra folder of skins to scan")
    mx.add_argument("--all-apps", action="store_true", help="also scan other Steam cursor apps")
    mx.add_argument("ids", nargs="*", help="only import these workshop item ids")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd is None:
        from .app import run_gui
        return run_gui(minimized=args.minimized)

    from .qtrender import ensure_qt_app
    ensure_qt_app()
    from . import paths
    from .config import Settings
    from .library import SkinLibrary

    library = SkinLibrary()
    settings = Settings()

    if args.cmd == "list":
        skins = library.search(args.search, args.category, True if args.animated else None)
        for s in skins:
            flag = " [animated]" if s.animated else ""
            print(f"{s.id:48} {s.name}{flag}")
        print(f"\n{len(skins)} skin(s)")
        return 0
    if args.cmd == "categories":
        for c in library.categories():
            print(f"{c:12} {len(library.search(category=c))}")
        return 0
    if args.cmd == "info":
        s = _find_skin(library, args.skin)
        print(f"{s.name}\n  id:       {s.id}\n  author:   {s.meta.author}\n  category: {s.meta.category}"
              f"\n  tags:     {', '.join(s.meta.tags)}\n  animated: {s.animated}\n  roles:    "
              f"{', '.join(sorted(r.value for r in s.provided_roles()))}")
        if s.meta.description:
            print(f"  {s.meta.description}")
        return 0
    if args.cmd == "apply":
        from .backends import BackendError, get_backend
        from .imaging import Adjustments
        s = _find_skin(library, args.skin)
        size = args.size or int(settings["size"])
        backend = get_backend()
        try:
            print(backend.apply(s, size, Adjustments.from_dict(settings.adjustments_for(s.id))))
        except BackendError as exc:
            print(exc, file=sys.stderr)
            return 1
        settings["skin"] = s.id
        settings["size"] = size
        settings.save()
        return 0
    if args.cmd == "restore":
        from .backends import get_backend
        print(get_backend().restore_default(previous=not args.default))
        return 0
    if args.cmd == "export":
        from .formats import packs
        s = _find_skin(library, args.skin)
        out = Path(args.output)
        if args.format == "windows":
            dest = packs.export_windows_pack(s, out, args.size)
        elif args.format == "xcursor":
            dest = packs.export_xcursor_theme(s, out.parent, out.name)
        elif args.format == "skin":
            dest = packs.export_skin(s, out, args.size)
        else:
            dest = packs.export_preview_png(s, out, args.size)
        print(f"Exported '{s.name}' to {dest}")
        return 0
    if args.cmd == "import-mousex":
        from .formats import mousex
        appids = tuple(mousex.KNOWN_APPS) if args.all_apps else (mousex.MOUSE_X_APPID,)
        extra = [Path(f) for f in args.folder] + mousex.mouse_x_local_skin_dirs()
        items = mousex.find_workshop_items(appids, extra)
        if args.ids:
            items = [i for i in items if i.item_id in args.ids]
        if args.online:
            mousex.lookup_titles(items)
        if not items:
            libs = ", ".join(str(p) for p in mousex.library_folders()) or "none found"
            print(f"No downloaded Mouse X workshop skins found (Steam libraries: {libs}).")
            return 1
        for i in items:
            print(f"{i.item_id:>14}  {i.app_name:14} {i.display_name}   [{i.path}]")
        if args.list:
            return 0
        ok = 0
        for i in items:
            try:
                dest = mousex.import_item(i, paths.skins_dir())
                ok += 1
                print(f"  imported -> {dest.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {i.item_id}: failed ({exc})", file=sys.stderr)
        print(f"Imported {ok} of {len(items)} item(s). Check hotspots in Studio > Pack Builder if needed.")
        return 0 if ok else 1
    if args.cmd == "import":
        from .formats import packs
        try:
            dest = packs.import_path(args.path, paths.skins_dir(), args.name)
        except (packs.ImportError_, ValueError, OSError) as exc:
            print(f"Import failed: {exc}", file=sys.stderr)
            return 1
        skin = library.add_from_path(dest)
        print(f"Imported '{skin.name}' as {skin.id}")
        return 0
    return 1
