"""Pick the right system-cursor backend for this platform."""

from __future__ import annotations

import sys

from .base import Backend, BackendError, NullBackend


def get_backend() -> Backend:
    if sys.platform == "win32":
        from .windows import WindowsBackend
        return WindowsBackend()
    if sys.platform.startswith(("linux", "freebsd", "openbsd", "netbsd")):
        from .linux import LinuxBackend
        return LinuxBackend()
    return NullBackend()


__all__ = ["Backend", "BackendError", "NullBackend", "get_backend"]
