import sys

import pytest

from mouze.backends import BackendError, get_backend
from mouze.builtin.catalog import builtin_skins
from mouze.roles import Role


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry backend")
def test_windows_apply_and_restore(qapp, monkeypatch):  # pragma: no cover - runs on Windows CI
    import winreg

    backend = get_backend()
    skin = next(s for s in builtin_skins() if s.id == "builtin:rgb-rgb-chroma-classic")

    def read(name):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors") as k:
            try:
                return winreg.QueryValueEx(k, name)[0]
            except FileNotFoundError:
                return None

    # Registry logic first, without asking Windows to reload (CI runners have no interactive desktop).
    reloads = []
    monkeypatch.setattr(backend, "_reload", lambda: reloads.append(1))
    before = read("Arrow")
    backend.apply(skin, 48)
    assert read("") == "MouZe"
    assert read("Arrow").endswith("arrow.ani")
    assert read("Hand").endswith("link.ani")
    assert read("CursorBaseSize") == 48
    backend.restore_default(previous=True)
    assert read("Arrow") == before
    assert len(reloads) == 2
    monkeypatch.undo()

    # Then the real reload, which needs an interactive session.
    try:
        backend.apply(skin, 32)
    except BackendError as exc:
        monkeypatch.setattr(backend, "_reload", lambda: None)
        backend.restore_default(previous=True)  # undo the registry change
        pytest.skip(f"no interactive desktop: {exc}")
    try:
        assert backend.current_role() in (None, *Role)
    finally:
        backend.restore_default(previous=True)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux backend")
def test_linux_backend_writes_theme(qapp, tmp_path, monkeypatch):
    from mouze.backends import linux

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    calls = []
    monkeypatch.setattr(linux, "_run", lambda *cmd, **kw: (calls.append(cmd) or True, ""))
    backend = linux.LinuxBackend()
    skin = builtin_skins()[0]
    msg = backend.apply(skin, 32)
    assert "Applied" in msg
    themes = list((tmp_path / "share" / "icons").glob("mouze-*"))
    assert len(themes) == 1 and (themes[0] / "cursors" / "left_ptr").exists()
    assert any(c[:2] == ("gsettings", "set") for c in calls)
    backend.restore_default()
    assert not list((tmp_path / "share" / "icons").glob("mouze-*"))
