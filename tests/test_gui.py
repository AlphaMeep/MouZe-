"""Smoke tests: build the whole UI offscreen and poke the main flows."""

import time

from mouze.controller import Controller
from mouze.library import SkinLibrary


def pump(ms=200):
    from PySide6.QtCore import QCoreApplication
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def test_main_window(qapp, fake_backend, tmp_settings, tmp_path):
    from mouze.gui.main_window import MainWindow
    c = Controller(tmp_settings, SkinLibrary(tmp_path / "skins"), fake_backend)
    w = MainWindow(c)
    c.start()
    w.show()
    pump(300)
    for i in range(w.nav.count()):
        w.nav.setCurrentRow(i)
        pump(50)
    # library: select + adjust + favourite
    w.library.select("builtin:neon-neon-magenta")
    pump(50)
    assert w.library.detail.skin.id == "builtin:neon-neon-magenta"
    w.library.detail.mirror.setChecked(True)
    assert c.adjustments("builtin:neon-neon-magenta").mirror
    w.library.toggle_favorite("builtin:neon-neon-magenta")
    assert "builtin:neon-neon-magenta" in tmp_settings["favorites"]
    w.library.search.setText("crosshair green")
    w.library.refilter()
    visible = [sid for sid, it in w.library.items.items() if not it.isHidden()]
    assert visible and all("crosshair" in sid for sid in visible)
    # designer save
    w.studio.designer.name.setText("Test Design")
    w.studio.designer.style.setCurrentIndex(w.studio.designer.style.findData("neon"))
    w.studio.designer.save(apply=True)
    pump(300)
    assert any(s.name == "Test Design" for s in c.library)
    assert c.skin.name == "Test Design"
    # remix
    w.library.remix_requested.emit("builtin:gradient-sunset")
    assert w.studio.designer.name.text() == "Sunset Remix"
    # effects overlay
    w.effects.enabled.setChecked(True)
    pump(100)
    assert c.overlay is not None and c.overlay.running
    w.effects.enabled.setChecked(False)
    w.quit()
