import pytest

from mouze.builtin.catalog import CATEGORIES, builtin_skins
from mouze.imaging import Adjustments
from mouze.roles import Role
from mouze.skin import FileSkin, load_skin, save_skin


@pytest.fixture(scope="module")
def skins(qapp):
    return builtin_skins()


def test_catalog_size_and_ids(skins):
    assert len(skins) >= 200
    ids = [s.id for s in skins]
    assert len(ids) == len(set(ids))
    assert {s.meta.category for s in skins} == set(CATEGORIES)
    assert any(s.animated for s in skins)


@pytest.mark.parametrize("size", [24, 32, 48, 96])
def test_every_role_renders_in_bounds(skins, size):
    sample = skins[:: max(1, len(skins) // 25)]
    for skin in sample:
        for role in Role:
            anim = skin.render(role, size)
            assert anim.frames, (skin.id, role)
            assert all(f.size == (size, size) for f in anim.frames)
            hx, hy = anim.hotspot
            assert 0 <= hx < size and 0 <= hy < size
            assert len(anim.delays) == len(anim.frames)
            assert anim.frames[0].getchannel("A").getbbox() is not None, (skin.id, role)


def test_busy_is_animated_everywhere(skins):
    for skin in skins[::20]:
        assert skin.render(Role.BUSY, 32).animated


def test_hotspot_positions(skins):
    light = next(s for s in skins if s.id == "builtin:classic-light")
    assert light.render(Role.ARROW, 32).hotspot == (3, 2)
    assert light.render(Role.MOVE, 32).hotspot == (16, 16)
    big = light.render(Role.ARROW, 64).hotspot
    assert big == (6, 4)


def test_adjustments_mirror_and_speed(skins):
    rgb = next(s for s in skins if s.animated)
    plain = rgb.render(Role.ARROW, 32)
    adj = Adjustments(mirror=True, speed=2.0, hue=90, opacity=0.5)
    out = rgb.render(Role.ARROW, 32, adj)
    assert out.hotspot[0] == 31 - plain.hotspot[0]
    assert out.delays[0] == max(10, round(plain.delays[0] / 2))
    assert out.frames[0].getchannel("A").getextrema()[1] <= 128


def test_adjustments_dict_roundtrip():
    adj = Adjustments(hue=20, mirror=True, tint="#ff0000")
    assert Adjustments.from_dict(adj.to_dict()) == adj
    assert Adjustments().to_dict() == {}
    assert Adjustments.from_dict({"unknown": 1}) == Adjustments()


def test_save_and_load_procedural(tmp_path, skins):
    skin = next(s for s in skins if s.meta.category == "Neon")
    dest = save_skin(skin, tmp_path / "neon.mouzeskin", size=48)
    back = load_skin(dest)
    assert getattr(back, "recipe", None) == skin.recipe
    assert back.name == skin.name


def test_save_with_adjustments_becomes_file_skin(tmp_path, skins):
    skin = next(s for s in skins if s.animated)
    dest = save_skin(skin, tmp_path / "tinted", size=32, adj=Adjustments(hue=120))
    back = load_skin(dest)
    assert isinstance(back, FileSkin)
    assert back.animated
    anim = back.render(Role.ARROW, 32)
    assert anim.animated and anim.frames[0].size == (32, 32)
    assert back.render(Role.ARROW, 64).hotspot[0] == 2 * anim.hotspot[0]


def test_file_skin_fallback_roles(tmp_path, qapp):
    from PIL import Image
    d = tmp_path / "mini"
    d.mkdir()
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(d / "a.png")
    (d / "skin.json").write_text('{"name": "Mini", "cursors": {"arrow": {"file": "a.png", "hotspot": [1, 1]}}}')
    skin = load_skin(d)
    assert skin.resolve_role(Role.PIN) == Role.ARROW
    assert skin.render(Role.BUSY, 32).hotspot == (1, 1)


def test_load_rejects_path_traversal(tmp_path, qapp):
    d = tmp_path / "evil"
    d.mkdir()
    (d / "skin.json").write_text('{"name": "Evil", "cursors": {"arrow": {"file": "../x.png"}}}')
    with pytest.raises(ValueError):
        load_skin(d)
