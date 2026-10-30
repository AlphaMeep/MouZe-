import io
import json
import os

from PIL import Image

from mouze import cli
from mouze.formats import mousex, mousex_inspect


def _png(w=32, h=32, frames=1):
    buf = io.BytesIO()
    imgs = [Image.new("RGBA", (w, h), (255, 0, i * 40, 255)) for i in range(frames)]
    imgs[0].save(buf, "PNG" if frames == 1 else "GIF", save_all=frames > 1, append_images=imgs[1:], duration=80)
    return buf.getvalue()


def _fake_steam(tmp_path, monkeypatch):
    home = tmp_path / "home" / "alice"
    steam = tmp_path / "Steam"
    apps = steam / "steamapps"
    install = apps / "common" / "Mouse X"
    (install / "MouseX_Data").mkdir(parents=True)
    (install / "UnityPlayer.dll").write_bytes(b"MZ" + b"\0" * 100)
    (install / "steam_api64.dll").write_bytes(b"MZ" + b"\0" * 10)
    (install / "MouseX_Data" / "globalgamemanagers").write_bytes(b"\0" * 40)
    (apps / f"appmanifest_{mousex.MOUSE_X_APPID}.acf").write_text('"AppState" { "installdir" "Mouse X" }')
    content = apps / "workshop" / "content" / str(mousex.MOUSE_X_APPID)
    plain = content / "111"
    plain.mkdir(parents=True)
    (plain / "normal.png").write_bytes(_png())
    (plain / "busy.gif").write_bytes(_png(frames=3))
    (plain / "skin.cfg").write_text("[cursor]\nhotspotX=3\nhotspotY=4\n")
    (plain / "meta.json").write_text(json.dumps({"title": "Spooky", "author": "artist", "hotspot": [3, 4],
                                                 "path": str(home / "secret")}))
    blob = content / "222"
    blob.mkdir()
    (blob / "skin.mxs").write_bytes(os.urandom(2048))
    appdata = home / "AppData" / "Roaming"
    (appdata / "CenterPoint" / "Mouse X").mkdir(parents=True)
    (appdata / "CenterPoint" / "Mouse X" / "settings.json").write_text(json.dumps({"size": 48, "speed": 1.5}))
    monkeypatch.setenv("MOUZE_STEAM_PATH", str(steam))
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("USERNAME", "alice")
    monkeypatch.setattr(mousex.Path, "home", staticmethod(lambda: home))
    return home


def test_report_describes_install_settings_and_items(tmp_path, monkeypatch, qapp):
    home = _fake_steam(tmp_path, monkeypatch)
    report = mousex_inspect.build_report()
    assert "Unity" in report and "Steamworks" in report
    assert "settings.json" in report and "`size`: int = 48" in report
    # both items appear, including the one the importer skips
    assert "item `111`" in report and "item `222`" in report
    assert "GIF 32×32" in report and "3 frames" in report
    assert "`hotspotX` = \"3\"" in report
    assert "unknown binary" in report and "looks compressed or encrypted" in report
    assert "skipped by the importer: yes" in report
    assert "detected as: **images**" in report and "busy: 3 frame(s)" in report
    # the skin-wide hotspot from meta.json reaches the arrow even though busy.gif is read first
    assert "arrow: 1 frame(s) 32×32, hotspot (3, 4)" in report
    # personal details are redacted
    assert str(home) not in report and "alice" not in report


def test_report_cli_writes_file(tmp_path, monkeypatch, qapp, capsys):
    _fake_steam(tmp_path, monkeypatch)
    out = tmp_path / "report.md"
    assert cli.main(["import-mousex", "--report", str(out)]) == 0
    assert out.read_text("utf-8").startswith("# Mouse X format report")
    assert "Saved the Mouse X format report" in capsys.readouterr().out


def test_describe_file_handles_bad_files(tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\nnope")
    assert "could not decode" in mousex_inspect.describe_file(bad)[0]
    js = tmp_path / "x.json"
    js.write_text("{not json")
    assert "does not parse" in mousex_inspect.describe_file(js)[0]
