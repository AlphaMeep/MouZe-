import pytest

from mouze.builtin.catalog import builtin_skins
from mouze.formats import packs
from mouze.formats.packs import _parse_inf
from mouze.roles import Role
from mouze.skin import load_skin


@pytest.fixture(scope="module")
def skin(qapp):
    return next(s for s in builtin_skins() if s.id == "builtin:rgb-rgb-chroma-modern")


def test_windows_pack_roundtrip(tmp_path, skin):
    out = packs.export_windows_pack(skin, tmp_path / "pack", 32)
    files = {p.name for p in out.iterdir()}
    assert "install.inf" in files and "arrow.ani" in files and "busy.ani" in files
    name, mapping = _parse_inf((out / "install.inf").read_text())
    assert name == skin.name
    assert mapping[Role.ARROW] == "arrow.ani"
    assert mapping[Role.PERSON] == "person.ani"
    dest = packs.import_path(out, tmp_path / "skins")
    back = load_skin(dest)
    assert back.provided_roles() == set(Role)
    assert back.render(Role.ARROW, 32).animated


def test_inf_with_custom_names(tmp_path):
    inf = r'''
[Version]
signature="$CHICAGO$"
[Scheme.Reg]
HKCU,"Control Panel\Cursors\Schemes","%SCHEME_NAME%",,"%10%\%CUR_DIR%\%pointer%,%10%\%CUR_DIR%\%help%,,%10%\%CUR_DIR%\%busy%"
[Strings]
CUR_DIR = "Cursors\Cool"
SCHEME_NAME = "Cool Pack"
pointer = "a1.cur"
help = "zz.cur"
busy = "spin.ani"
'''
    name, mapping = _parse_inf(inf)
    assert name == "Cool Pack"
    assert mapping == {Role.ARROW: "a1.cur", Role.HELP: "zz.cur", Role.BUSY: "spin.ani"}


def test_xcursor_theme_roundtrip(tmp_path, skin):
    root = packs.export_xcursor_theme(skin, tmp_path, "test-theme", sizes=(24, 32))
    assert (root / "cursors" / "left_ptr").exists()
    assert (root / "cursors" / "pointer").exists()
    assert "Name=test-theme" in (root / "index.theme").read_text()
    dest = packs.import_path(root, tmp_path / "skins")
    back = load_skin(dest)
    assert Role.LINK in back.provided_roles()
    assert back.render(Role.ARROW, 32).frames[0].size == (32, 32)


def test_loose_image_import(tmp_path, qapp):
    from PIL import Image
    src = tmp_path / "src"
    src.mkdir()
    Image.new("RGBA", (40, 40), (0, 0, 255, 255)).save(src / "Busy.gif")
    Image.new("RGBA", (40, 40), (0, 255, 0, 255)).save(src / "pointer.png")
    dest = packs.import_path(src, tmp_path / "skins", name="Loose")
    back = load_skin(dest)
    assert back.name == "Loose"
    assert {Role.BUSY, Role.LINK} <= back.provided_roles() or Role.ARROW in back.provided_roles()


def test_zip_import_and_unsupported(tmp_path, skin):
    z = packs.export_skin(skin, tmp_path / "s.mouzeskin", 32)
    dest = packs.import_path(z, tmp_path / "skins", name="Zipped")
    assert load_skin(dest).name == "Zipped"
    bad = tmp_path / "x.txt"
    bad.write_text("hi")
    with pytest.raises(packs.ImportError_):
        packs.import_path(bad, tmp_path / "skins")


def test_preview_png(tmp_path, skin):
    out = packs.export_preview_png(skin, tmp_path / "p.png", 32)
    assert out.stat().st_size > 1000
