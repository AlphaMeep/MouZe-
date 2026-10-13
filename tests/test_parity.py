"""Tests for the Mouse X parity features: community catalogs, per-skin size,
seasonal Discover content, localization and editing existing skins."""

import json
import sys
import time
from pathlib import Path

import pytest

from mouze import community, i18n
from mouze.builtin.catalog import SEASON_BY_MONTH, STAFF_PICKS, builtin_skins
from mouze.controller import Controller
from mouze.library import SkinLibrary
from mouze.skin import load_skin, save_skin

ROOT = Path(__file__).resolve().parents[1]


def pump(ms=150):
    from PySide6.QtCore import QCoreApplication
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


@pytest.fixture
def catalog(tmp_path, qapp):
    skins = [s for s in builtin_skins() if s.meta.category == "Glass"][:2]
    (tmp_path / "cat" / "skins").mkdir(parents=True)
    entries = []
    for i, s in enumerate(skins):
        save_skin(s, tmp_path / "cat" / "skins" / f"s{i}.mouzeskin", size=32)
        entries.append({"id": f"s{i}", "name": f"Community {i}", "author": "tester", "version": "1.0",
                        "url": f"skins/s{i}.mouzeskin", "tags": ["test"]})
    index = tmp_path / "cat" / "index.json"
    index.write_text(json.dumps({"name": "Test Catalog", "skins": entries}))
    return index


def test_catalog_subscribe_update_unsubscribe(catalog, tmp_settings, tmp_path):
    name, entries = community.fetch_catalog(str(catalog))
    assert name == "Test Catalog" and len(entries) == 2
    assert Path(entries[0].url).exists()
    skins_dir = tmp_path / "skins"
    folder = community.subscribe(entries[0], tmp_settings, skins_dir)
    sub = tmp_settings["subscriptions"][entries[0].key]
    assert sub["version"] == "1.0" and folder.name == "community-s0"
    skin = load_skin(folder)
    assert skin.name == "Community 0" and "community" in skin.meta.tags
    # nothing changed -> no update
    assert community.update_subscriptions(tmp_settings, skins_dir) == []
    # bump the version in the catalog -> re-downloaded
    data = json.loads(catalog.read_text())
    data["skins"][0]["version"] = "1.1"
    catalog.write_text(json.dumps(data))
    assert community.update_subscriptions(tmp_settings, skins_dir) == ["Community 0"]
    assert tmp_settings["subscriptions"][entries[0].key]["version"] == "1.1"
    community.unsubscribe(entries[0].key, tmp_settings, skins_dir)
    assert not folder.exists() and not tmp_settings["subscriptions"]


def test_repo_community_catalog_is_valid(qapp):
    index = ROOT / "community" / "index.json"
    name, entries = community.fetch_catalog(str(index))
    assert entries and name
    for e in entries:
        assert Path(e.url).exists(), e.url
        assert Path(e.preview).exists(), e.preview
        load_skin(Path(e.url))


def test_per_skin_size(qapp, fake_backend, tmp_settings, tmp_path):
    c = Controller(tmp_settings, SkinLibrary(tmp_path / "skins"), fake_backend)
    tmp_settings["size"] = 32
    c.apply_skin("builtin:classic-light")
    c.set_skin_size("builtin:classic-light", 64)
    assert c.size() == 64
    assert c.size("builtin:classic-dark") == 32
    c.step_size(1)  # hotkeys change the active skin's own size
    assert tmp_settings["skin_sizes"]["builtin:classic-light"] == 72
    assert tmp_settings["size"] == 32
    c.set_skin_size("builtin:classic-light", None)
    assert c.size() == 32
    c.hotkeys.stop()


def test_seasonal_and_picks(qapp):
    ids = {s.id for s in builtin_skins()}
    assert all(p in ids for p in STAFF_PICKS)
    seasonal = [s for s in builtin_skins() if s.meta.category == "Seasonal"]
    for month, tags in SEASON_BY_MONTH.items():
        assert any(any(t in s.meta.tags for t in tags) for s in seasonal), month
    assert any("halloween" in s.meta.tags for s in seasonal)


def test_translations_complete():
    sys.path.insert(0, str(ROOT / "scripts"))
    import i18n_strings
    strings = i18n_strings.collect()
    assert len(strings) > 300
    for code in i18n.LANGUAGES:
        if code == "en":
            continue
        table = json.loads((ROOT / "mouze" / "i18n" / f"{code}.json").read_text("utf-8"))
        missing = [s for s in strings if s not in table]
        assert not missing, (code, missing[:5])


def test_tr_and_language_switch(monkeypatch):
    assert i18n.set_language("zh_CN") == "zh_CN"
    assert i18n.tr("Apply") == "应用"
    assert i18n.tr("{n} of {total} skins").format(n=1, total=2) == "1 / 2 个皮肤"
    assert i18n.set_language("nonexistent") == "en"
    assert i18n.tr("Apply") == "Apply"
    monkeypatch.setenv("MOUZE_LANG", "zh_TW")
    assert i18n.system_language() == "zh_TW"
    monkeypatch.setenv("MOUZE_LANG", "pt_PT")
    assert i18n.system_language() == "pt_BR"
    i18n.set_language("en")


def test_gui_new_pages(qapp, fake_backend, tmp_settings, tmp_path, catalog, monkeypatch):
    from mouze import paths
    from mouze.formats import packs
    from mouze.gui.main_window import PAGE, MainWindow
    monkeypatch.setattr(paths, "skins_dir", lambda: tmp_path / "skins")
    tmp_settings["catalogs"] = [str(catalog)]
    c = Controller(tmp_settings, SkinLibrary(tmp_path / "skins"), fake_backend)
    w = MainWindow(c)
    w.show()
    # Discover: local sections + community catalog from a local index
    w.nav.setCurrentRow(PAGE["Discover"])
    for _ in range(60):
        pump(50)
        if w.discover.community_cards:
            break
    assert w.discover.community_cards
    card = next(iter(w.discover.community_cards.values()))
    card.toggle()
    assert c.settings["subscriptions"]
    assert any(s.name.startswith("Community") for s in c.library)
    w.discover.open_skin.emit("builtin:glass-glass-clear")
    assert w.nav.currentRow() == PAGE["Library"]
    assert w.library.detail.skin.id == "builtin:glass-glass-clear"
    # Help page renders
    w.nav.setCurrentRow(PAGE["Help"])
    pump(50)
    # per-skin size from the library panel
    d = w.library.detail
    d.own_size.setChecked(True)
    d.size.setCurrentIndex(d.size.findData(48))
    assert c.skin_size("builtin:glass-glass-clear") == 48
    # edit an imported skin in the Pack Builder and save in place
    src = tmp_path / "pack"
    src.mkdir()
    from PIL import Image
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(src / "arrow.png")
    dest = packs.import_path(src, tmp_path / "skins", name="Editable")
    skin = c.library.add_from_path(dest)
    w.library.edit_requested.emit(skin.id)
    builder = w.studio.builder
    assert builder.editing == dest and builder.entries
    builder._hotspot_clicked(7, 9)
    builder.save()
    reloaded = load_skin(dest)
    assert reloaded.render(next(iter(reloaded.provided_roles())), 32).hotspot == (7, 9)
    assert not list((tmp_path / "skins").glob(".staging*"))
    # Mouse X dialog opens and scans without Steam installed
    from mouze.gui.mousex_dialog import MouseXDialog
    monkeypatch.setenv("MOUZE_STEAM_PATH", str(tmp_path / "nosteam"))
    dlg = MouseXDialog(c, w)
    assert dlg.status.text()
    dlg.close()
    w.quit()
