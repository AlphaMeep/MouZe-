import datetime as dt
import time

from mouze.controller import Controller, in_time_window, rule_matches
from mouze.library import SkinLibrary


def wait_for(cond, timeout=5.0):
    from PySide6.QtCore import QCoreApplication
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_time_windows():
    assert in_time_window("")
    assert in_time_window("09:00-17:00", dt.time(12, 0))
    assert not in_time_window("09:00-17:00", dt.time(18, 0))
    assert in_time_window("19:00-07:00", dt.time(23, 30))
    assert in_time_window("19:00-07:00", dt.time(6, 59))
    assert not in_time_window("19:00-07:00", dt.time(12, 0))
    assert not in_time_window("garbage", dt.time(12, 0))


def test_rule_matching():
    r = {"process": "game.exe, *valorant*", "enabled": True}
    assert rule_matches(r, "game.exe")
    assert rule_matches(r, "valorant-win64-shipping.exe")
    assert not rule_matches(r, "notepad.exe")
    assert not rule_matches(r, None)
    assert rule_matches({"process": "code"}, "code.exe")
    assert not rule_matches({"process": "game.exe", "enabled": False}, "game.exe")
    assert not rule_matches({}, "game.exe")
    assert rule_matches({"time": "00:00-23:59"}, None, dt.time(10, 0))


def make(qapp, fake_backend, tmp_settings, tmp_path):
    lib = SkinLibrary(tmp_path / "skins")
    return Controller(tmp_settings, lib, fake_backend)


def test_apply_and_cycle(qapp, fake_backend, tmp_settings, tmp_path):
    c = make(qapp, fake_backend, tmp_settings, tmp_path)
    c.apply_skin("builtin:neon-neon-cyan")
    assert wait_for(lambda: fake_backend.applied)
    assert fake_backend.applied[-1][0] == "builtin:neon-neon-cyan"
    assert tmp_settings["skin"] == "builtin:neon-neon-cyan"
    assert tmp_settings["recent"][0] == "builtin:neon-neon-cyan"
    tmp_settings["favorites"] = ["builtin:classic-light", "builtin:classic-dark"]
    c.apply_skin("builtin:classic-light")
    c.cycle(1)
    assert c.active_skin_id == "builtin:classic-dark"
    c.cycle(1)
    assert c.active_skin_id == "builtin:classic-light"
    c.hotkeys.stop()


def test_size_steps(qapp, fake_backend, tmp_settings, tmp_path):
    c = make(qapp, fake_backend, tmp_settings, tmp_path)
    tmp_settings["size"] = 32
    c.step_size(1)
    assert tmp_settings["size"] == 40
    c.step_size(-1)
    c.step_size(-1)
    assert tmp_settings["size"] == 24
    c.set_size(1000)
    assert tmp_settings["size"] == 256
    c.hotkeys.stop()


def test_profiles_switch_and_restore(qapp, fake_backend, tmp_settings, tmp_path):
    c = make(qapp, fake_backend, tmp_settings, tmp_path)
    tmp_settings["skin"] = "builtin:classic-light"
    tmp_settings["effects"]["enabled"] = False
    tmp_settings["profiles"]["rules"] = [
        {"name": "Game", "process": "game.exe", "skin": "builtin:crosshair-gap-cross-green", "size": 48,
         "effects": "off", "enabled": True},
        {"name": "Night", "time": "22:00-06:00", "skin": "builtin:classic-dark", "effects": "on", "enabled": True},
    ]
    m = c.evaluate_profiles("game.exe", dt.time(12, 0))
    assert m["name"] == "Game"
    assert c.active_skin_id == "builtin:crosshair-gap-cross-green"
    assert c.size() == 48
    m = c.evaluate_profiles("notepad.exe", dt.time(23, 0))
    assert m["name"] == "Night"
    assert c.active_skin_id == "builtin:classic-dark"
    assert tmp_settings["effects"]["enabled"] is True
    m = c.evaluate_profiles("notepad.exe", dt.time(12, 0))
    assert m is None
    assert c.active_skin_id == "builtin:classic-light"
    assert tmp_settings["effects"]["enabled"] is False
    assert tmp_settings["skin"] == "builtin:classic-light"  # profile switches never persist
    c.set_effects_enabled(False)
    c.hotkeys.stop()


def test_unknown_skin_falls_back(qapp, fake_backend, tmp_settings, tmp_path):
    c = make(qapp, fake_backend, tmp_settings, tmp_path)
    c.apply_skin("builtin:does-not-exist")
    assert c.active_skin_id is not None and c.library.get(c.active_skin_id)
    c.hotkeys.stop()
