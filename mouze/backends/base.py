"""Backend interface: how a skin gets onto the real system cursor."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .. import paths
from ..imaging import Adjustments
from ..roles import Role
from ..skin import Skin, slugify


class BackendError(RuntimeError):
    pass


class Backend:
    name = "none"
    supports_native = False
    supports_role_detection = False
    notes = ""

    def apply(self, skin: Skin, size: int, adj: Adjustments | None = None) -> str:
        """Make ``skin`` the system cursor.  Returns a human readable status."""
        raise BackendError(self.notes or "Changing the system cursor is not supported on this platform.")

    def restore_default(self, previous: bool = True) -> str:
        """Put back the cursors that were active before MouZe (or the OS defaults)."""
        return "Nothing to restore."

    def hide(self) -> str:
        """Make the system cursor invisible (used by overlay-cursor mode)."""
        raise BackendError("Hiding the system cursor is not supported on this platform.")

    def current_role(self) -> Role | None:
        return None

    # helpers -------------------------------------------------------------------
    @staticmethod
    def output_dir(skin: Skin, size: int, adj: Adjustments | None) -> Path:
        key = hashlib.sha1(repr((skin.id, size, adj.key() if adj else ())).encode()).hexdigest()[:8]
        d = paths.generated_dir() / f"{slugify(skin.name)}-{size}-{key}"
        return d

    @staticmethod
    def clean_generated(keep: Path | None) -> None:
        root = paths.generated_dir()
        if not root.is_dir():
            return
        for d in root.iterdir():
            if d.is_dir() and (keep is None or d.resolve() != keep.resolve()):
                shutil.rmtree(d, ignore_errors=True)


class NullBackend(Backend):
    name = "unsupported"
    notes = ("This platform does not allow apps to replace the system cursor. "
             "Cursor effects (trails, click ripples, spotlight) still work.")
