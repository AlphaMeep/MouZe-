import json

import pytest

from mouze.config import DEFAULTS, Settings, deep_merge
from mouze.system.hotkeys import parse_hotkey, to_pynput, vk_code


def test_deep_merge_keeps_new_defaults():
    merged = deep_merge(DEFAULTS, {"effects": {"trail": {"color": "#123456"}}, "size": 48})
    assert merged["effects"]["trail"]["color"] == "#123456"
    assert merged["effects"]["trail"]["length"] == DEFAULTS["effects"]["trail"]["length"]
    assert merged["size"] == 48


def test_settings_save_load_and_broken(tmp_path):
    p = tmp_path / "s.json"
    s = Settings(p)
    s["size"] = 64
    s.toggle_favorite("x")
    s.save()
    s2 = Settings(p)
    assert s2["size"] == 64 and s2["favorites"] == ["x"]
    assert s2.toggle_favorite("x") is False
    p.write_text("{not json")
    s3 = Settings(p)
    assert s3["size"] == DEFAULTS["size"]
    assert (tmp_path / "s.broken.json").exists()


def test_hotkey_parsing():
    assert parse_hotkey("Ctrl+Alt+E") == ({"ctrl", "alt"}, "e")
    assert parse_hotkey("super+shift+f5") == ({"win", "shift"}, "f5")
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+alt")
    with pytest.raises(ValueError):
        parse_hotkey("a+b")
    assert vk_code("e") == ord("E")
    assert vk_code("f1") == 0x70
    assert vk_code("right") == 0x27
    assert to_pynput("ctrl+alt+right") == "<ctrl>+<alt>+<right>"
    assert to_pynput("shift+win+k") == "<shift>+<cmd>+k"
    assert to_pynput("ctrl+pageup") == "<ctrl>+<page_up>"


def test_seq_conversion(qapp):
    from mouze.gui.settings_page import hotkey_to_seq, seq_to_hotkey
    for hk in ("ctrl+alt+e", "ctrl+alt+right", "ctrl+shift+pageup", "alt+f4"):
        assert seq_to_hotkey(hotkey_to_seq(hk)) == hk


def test_defaults_are_json_serialisable():
    json.dumps(DEFAULTS)
