import base64
import io
import json
import zipfile

import pytest
from PIL import Image

from mouze.builtin.catalog import builtin_skins
from mouze.formats import mousex, packs, platforms
from mouze.roles import Role
from mouze.skin import load_skin


def png_bytes(color=(255, 0, 0, 255), size=(32, 32), dot=None):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    for y in range(size[1] // 2):
        for x in range(y + 1):
            img.putpixel((x + 2, y + 3), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def skin(qapp):
    return next(s for s in builtin_skins() if s.id == "builtin:rgb-rgb-chroma-modern")


def test_mousecape_roundtrip(tmp_path, skin):
    cape = packs.export_mousecape(skin, tmp_path / "x", 32)
    assert cape.suffix == ".cape"
    meta, cursors = platforms.read_mousecape(cape.read_bytes())
    assert meta.name == skin.name
    assert {Role.ARROW, Role.TEXT, Role.LINK, Role.BUSY, Role.SIZE_NS} <= set(cursors)
    arrow = cursors[Role.ARROW]
    original = skin.render(Role.ARROW, 64)
    assert arrow.animated and len(arrow.frames) == len(original.frames)
    assert arrow.hotspot == original.hotspot  # 2x representation picked, hotspot scaled
    dest = packs.import_path(cape, tmp_path / "skins")
    assert load_skin(dest).render(Role.LINK, 32).animated


def test_hyprcursor_theme(tmp_path, qapp):
    theme = tmp_path / "MyHypr"
    (theme / "hyprcursors").mkdir(parents=True)
    (theme / "manifest.hl").write_text("name = My Hypr\ndescription = test\ncursors_directory = hyprcursors\n")
    with zipfile.ZipFile(theme / "hyprcursors" / "left_ptr.hlc", "w") as zf:
        zf.writestr("meta.hl", "hotspot_x = 0.25\nhotspot_y = 0.5\ndefine_override = default;arrow\n"
                               "define_size = 32, a.png, 40\ndefine_size = 32, b.png, 40\n")
        zf.writestr("a.png", png_bytes())
        zf.writestr("b.png", png_bytes((0, 255, 0, 255)))
    src = theme / "hyprcursors" / "pointer"
    src.mkdir()
    (src / "meta.hl").write_text("hotspot_x = 0.5\nhotspot_y = 0.0\ndefine_size = 48, p.png\n")
    (src / "p.png").write_bytes(png_bytes(size=(48, 48)))
    assert packs.detect_kind(theme) == "hyprcursor"
    dest = packs.import_path(theme, tmp_path / "skins")
    s = load_skin(dest)
    assert s.name == "My Hypr"
    arrow = s.render(Role.ARROW, 32)
    assert arrow.animated and arrow.hotspot == (8, 16)
    assert s.render(Role.LINK, 48).hotspot == (24, 0)


def test_xcursorgen_sources(tmp_path, qapp):
    root = tmp_path / "theme-src"
    (root / "config").mkdir(parents=True)
    (root / "pngs").mkdir()
    (root / "pngs" / "left_ptr.png").write_bytes(png_bytes(size=(24, 24)))
    (root / "pngs" / "left_ptr_48.png").write_bytes(png_bytes(size=(48, 48)))
    (root / "pngs" / "w1.png").write_bytes(png_bytes(size=(48, 48)))
    (root / "pngs" / "w2.png").write_bytes(png_bytes((0, 0, 255, 255), size=(48, 48)))
    (root / "config" / "left_ptr.cursor").write_text("24 3 2 left_ptr.png\n48 6 4 left_ptr_48.png\n")
    (root / "config" / "watch.cursor").write_text("48 24 24 w1.png 30\n48 24 24 w2.png 30\n")
    assert packs.detect_kind(root) == "xcursorgen"
    s = load_skin(packs.import_path(root, tmp_path / "skins"))
    assert s.render(Role.ARROW, 48).hotspot == (6, 4)
    busy = s.render(Role.BUSY, 48)
    assert busy.animated and busy.delays == [30, 30]


def test_css_pack_roundtrip_and_data_uri(tmp_path, skin):
    out = packs.export_css(skin, tmp_path / "web", 32)
    css = (out / "mouze-cursors.css").read_text()
    assert "cursor: url(\"link.png\")" in css and ", pointer;" in css
    dest = packs.import_path(out, tmp_path / "skins")
    back = load_skin(dest)
    assert {Role.ARROW, Role.LINK, Role.TEXT, Role.BUSY} <= back.provided_roles()
    assert back.render(Role.ARROW, 32).hotspot == skin.render(Role.ARROW, 32).hotspot
    # a single stylesheet with an inline data: URI (as used by browser extensions)
    uri = "data:image/png;base64," + base64.b64encode(png_bytes()).decode()
    one = tmp_path / "inline.css"
    one.write_text(f"body {{ cursor: url('{uri}') 2 3, auto !important; }}\n"
                   "a:hover { cursor: url(https://example.com/x.png), pointer; }")
    s = load_skin(packs.import_path(one, tmp_path / "skins"))
    assert s.provided_roles() == {Role.ARROW}
    assert s.render(Role.ARROW, 32).hotspot == (2, 3)


def test_smart_folder_sequences_and_metadata(tmp_path, qapp):
    root = tmp_path / "SomePack"
    (root / "busy").mkdir(parents=True)
    for i in range(4):
        (root / "busy" / f"{i}.png").write_bytes(png_bytes((i * 60, 0, 0, 255)))
    for i in range(1, 4):
        (root / f"cursor_{i:02d}.png").write_bytes(png_bytes())
    (root / "hand.gif").write_bytes(png_bytes())
    (root / "preview.png").write_bytes(png_bytes())
    (root / "config.json").write_text(json.dumps({"name": "Fancy Pack", "author": "Someone",
                                                 "cursor": {"image": "cursor_01.png", "hotspot": {"x": 5, "y": 6},
                                                            "fps": 20}}))
    assert packs.detect_kind(root) == "images"
    s = load_skin(packs.import_path(root, tmp_path / "skins"))
    assert s.name == "Fancy Pack" and s.meta.author == "Someone"
    arrow = s.render(Role.ARROW, 32)
    assert arrow.animated and len(arrow.frames) == 3
    assert arrow.hotspot == (5, 6) and arrow.delays[0] == 50
    busy = s.render(Role.BUSY, 32)
    assert len(busy.frames) == 4 and busy.hotspot[0] > 5  # centred auto-hotspot
    assert Role.LINK in s.provided_roles()


def test_auto_hotspot(qapp):
    img = Image.open(io.BytesIO(png_bytes()))
    assert platforms.auto_hotspot(img, Role.ARROW) == (2, 3)
    cx, cy = platforms.auto_hotspot(img, Role.BUSY)
    assert cx > 2 and cy > 3


def test_steam_library_discovery_and_import(tmp_path, monkeypatch, qapp):
    steam = tmp_path / "Steam"
    lib2 = tmp_path / "Games"
    (steam / "steamapps").mkdir(parents=True)
    (lib2 / "steamapps").mkdir(parents=True)
    p0, p1 = (str(p).replace("\\", "\\\\") for p in (steam, lib2))
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n "0"\n {{\n  "path"  "{p0}"\n }}\n "1"\n {{\n  "path"  "{p1}"\n }}\n}}\n')
    item = lib2 / "steamapps" / "workshop" / "content" / str(mousex.MOUSE_X_APPID) / "3141592653"
    item.mkdir(parents=True)
    (item / "normal.png").write_bytes(png_bytes())
    (item / "info.json").write_text(json.dumps({"title": "Neon Thing", "creator": "artist"}))
    empty = item.parent / "999"
    empty.mkdir()
    monkeypatch.setenv("MOUZE_STEAM_PATH", str(steam))
    monkeypatch.setattr(mousex.Path, "home", staticmethod(lambda: tmp_path / "nohome"))
    assert lib2.resolve() in mousex.library_folders()
    items = mousex.find_workshop_items()
    assert [i.item_id for i in items] == ["3141592653"]
    assert items[0].title == "Neon Thing" and items[0].app_name == "Mouse X"
    dest = mousex.import_item(items[0], tmp_path / "skins")
    data = json.loads((dest / "skin.json").read_text())
    assert data["category"] == "Mouse X" and data["source"]["workshop_id"] == "3141592653"
    assert data["author"] == "artist"
    assert load_skin(dest).name == "Neon Thing"


def test_vdf_parsing():
    text = '"libraryfolders" { "0" { "path" "C:\\\\Program Files (x86)\\\\Steam" } "1" { "path" "D:\\\\SteamLibrary" } }'
    paths = mousex.parse_library_folders(text)
    assert [str(p).replace("/", "\\") for p in paths][1].endswith("SteamLibrary")
