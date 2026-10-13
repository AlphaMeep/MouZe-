import os
import sys
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_home = tempfile.mkdtemp(prefix="mouze-test-")
os.environ["MOUZE_HOME"] = _home
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


class FakeBackend:
    name = "fake"
    supports_native = True
    supports_role_detection = False
    notes = "fake backend for tests"

    def __init__(self):
        self.applied = []
        self.restored = 0

    def apply(self, skin, size, adj=None):
        self.applied.append((skin.id, size, adj))
        return f"applied {skin.id}"

    def restore_default(self, previous=True):
        self.restored += 1
        return "restored"

    def hide(self):
        raise RuntimeError("not supported")

    def current_role(self):
        return None


@pytest.fixture
def fake_backend():
    return FakeBackend()


@pytest.fixture
def tmp_settings(tmp_path):
    from mouze.config import Settings
    return Settings(tmp_path / "settings.json")
