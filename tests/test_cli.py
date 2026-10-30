import json

import pytest

from mouze import cli
from mouze.config import Settings


@pytest.fixture
def run(qapp, capsys):
    def _run(*argv):
        code = cli.main(list(argv))
        out = capsys.readouterr()
        return code, out.out, out.err
    return _run


def test_list_info_and_categories(run):
    code, out, _ = run("list", "--category", "Neon")
    assert code == 0 and "builtin:" in out and "skin(s)" in out
    code, out, _ = run("info", "Vaporwave")
    assert code == 0 and "builtin:gradient-vaporwave" in out
    code, out, _ = run("categories")
    assert code == 0 and "Classic" in out


def test_unknown_skin_exits(run):
    with pytest.raises(SystemExit, match="no skin matches"):
        run("info", "definitely-not-a-skin-xyz")


@pytest.mark.parametrize("fmt, name, check", [
    ("windows", "pack", lambda p: (p / "install.inf").exists()),
    ("xcursor", "theme", lambda p: (p / "index.theme").exists() and (p / "cursors" / "left_ptr").exists()),
    ("cape", "skin.cape", lambda p: p.read_bytes().startswith(b"<?xml")),
    ("css", "web", lambda p: (p / "mouze-cursors.css").exists()),
    ("skin", "skin.mouzeskin", lambda p: p.stat().st_size > 0),
    ("preview", "sheet.png", lambda p: p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"),
])
def test_export_every_format(run, tmp_path, fmt, name, check):
    out = tmp_path / name
    code, text, err = run("export", "Vaporwave", "-f", fmt, "-o", str(out), "--size", "32")
    assert code == 0, err
    assert "Exported 'Vaporwave'" in text
    assert check(out)


def test_export_uses_saved_adjustments(run, tmp_path):
    settings = Settings()
    settings.set_adjustments("builtin:gradient-vaporwave", {"invert": True})
    settings.save()
    try:
        run("export", "Vaporwave", "-f", "preview", "-o", str(tmp_path / "adj.png"), "--size", "32")
        run("export", "Vaporwave", "-f", "preview", "-o", str(tmp_path / "raw.png"), "--size", "32", "--raw")
    finally:
        settings = Settings()
        settings.set_adjustments("builtin:gradient-vaporwave", {})
        settings.save()
    assert (tmp_path / "adj.png").read_bytes() != (tmp_path / "raw.png").read_bytes()


def test_size_for_prefers_per_skin_size(tmp_settings):
    tmp_settings["size"] = 40
    assert tmp_settings.size_for("builtin:x") == 40
    tmp_settings["skin_sizes"]["builtin:x"] = 72
    assert tmp_settings.size_for("builtin:x") == 72
    assert tmp_settings.size_for(None) == 40
    tmp_settings["skin_sizes"]["builtin:x"] = "junk"
    assert tmp_settings.size_for("builtin:x") == 40


def test_import_command(run, tmp_path):
    skin_file = tmp_path / "v.mouzeskin"
    assert run("export", "Vaporwave", "-f", "skin", "-o", str(skin_file))[0] == 0
    code, out, _ = run("import", str(skin_file), "--name", "CLI Import Test")
    assert code == 0 and "Imported 'CLI Import Test'" in out
    code, _, err = run("import", str(tmp_path / "missing.zip"))
    assert code == 1 and "Import failed" in err


def test_settings_file_is_valid_json_after_cli(run):
    run("list")
    from mouze import paths
    if paths.settings_file().exists():
        json.loads(paths.settings_file().read_text("utf-8"))


def test_apply_respects_per_skin_size(run, monkeypatch, fake_backend):
    import mouze.backends as backends
    monkeypatch.setattr(backends, "get_backend", lambda: fake_backend)
    settings = Settings()
    original = json.loads(json.dumps(settings.data))
    settings["size"] = 32
    settings["skin_sizes"]["builtin:gradient-vaporwave"] = 80
    settings.save()
    try:
        assert run("apply", "Vaporwave")[0] == 0
        assert fake_backend.applied[-1][:2] == ("builtin:gradient-vaporwave", 80)
        # --size updates the skin's own size, leaving the global size alone
        assert run("apply", "Vaporwave", "--size", "500")[0] == 0
        assert fake_backend.applied[-1][1] == 256
        saved = Settings()
        assert saved["skin_sizes"]["builtin:gradient-vaporwave"] == 256 and saved["size"] == 32
    finally:
        settings = Settings()
        settings.data = original
        settings.save()
