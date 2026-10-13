"""Application controller: owns settings, the library, the backend, the overlay,
hotkeys, per-app profiles and the skin shuffler.  The GUI and tray talk to it."""

from __future__ import annotations

import atexit
import datetime as dt
import fnmatch
import logging
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from . import paths
from .backends import BackendError, get_backend
from .config import Settings
from .imaging import Adjustments
from .library import SkinLibrary
from .skin import Skin
from .system import foreground
from .system.hotkeys import HotkeyManager

log = logging.getLogger(__name__)

SIZES = [16, 24, 32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 160, 192, 224, 256]


def in_time_window(window: str, now: dt.time | None = None) -> bool:
    """``"19:00-07:00"`` style windows; wraps past midnight."""
    window = (window or "").strip()
    if not window:
        return True
    try:
        a, b = [s.strip() for s in window.split("-", 1)]
        start = dt.time.fromisoformat(a.zfill(5))
        end = dt.time.fromisoformat(b.zfill(5))
    except ValueError:
        return False
    now = now or dt.datetime.now().time()
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def rule_matches(rule: dict, process: str | None, now: dt.time | None = None) -> bool:
    if not rule.get("enabled", True):
        return False
    procs = [p.strip().lower() for p in (rule.get("process") or "").split(",") if p.strip()]
    window = (rule.get("time") or "").strip()
    if not procs and not window:
        return False
    if procs:
        if not process:
            return False
        if not any(fnmatch.fnmatch(process, p) or fnmatch.fnmatch(process, p + ".exe") for p in procs):
            return False
    return in_time_window(window, now)


class Controller(QObject):
    skin_changed = Signal(str)          # skin id actually on screen
    status = Signal(str)                # human readable status line
    busy_changed = Signal(bool)
    effects_changed = Signal(bool)
    settings_changed = Signal()
    show_window_requested = Signal()
    _hotkey = Signal(str)
    _apply_done = Signal(str, str, bool)  # skin id, message, ok
    _apply_idle = Signal()

    def __init__(self, settings: Settings | None = None, library: SkinLibrary | None = None,
                 backend=None, parent=None):
        super().__init__(parent)
        paths.ensure_dirs()
        self.settings = settings or Settings()
        self.library = library or SkinLibrary()
        self.backend = backend or get_backend()
        self.overlay = None
        self.active_skin_id: str | None = None
        self.override_rule: dict | None = None
        self._apply_lock = threading.Lock()
        self._pending = None
        self._applying = False
        self._hidden = False
        self.last_foreground = None
        self._effects_before: bool | None = None

        self._hotkey.connect(self.handle_action)
        self._apply_done.connect(self._on_apply_done)
        self._apply_idle.connect(lambda: self.busy_changed.emit(False))
        self.hotkeys = HotkeyManager(lambda action: self._hotkey.emit(action))

        self.watch_timer = QTimer(self)
        self.watch_timer.timeout.connect(self._watch)
        self.watch_timer.start(1500)
        self.shuffle_timer = QTimer(self)
        self.shuffle_timer.timeout.connect(self.shuffle_now)
        self._locator_timer = QTimer(self)
        self._locator_timer.setSingleShot(True)
        self._locator_timer.timeout.connect(self._maybe_stop_overlay)
        atexit.register(self._emergency_restore)

    # ------------------------------------------------------------------ startup
    def start(self) -> None:
        s = self.settings
        if s.get("cursor_hidden"):
            # We crashed while the overlay cursor had hidden the OS cursor.
            s["cursor_hidden"] = False
            s.save()
            self._safe_restore()
        if s["apply_on_start"] and self.backend.supports_native:
            self.apply_skin(s["skin"])
        else:
            self.active_skin_id = s["skin"]
        self.refresh_hotkeys()
        self.refresh_effects()
        self.refresh_shuffle()

    def shutdown(self) -> None:
        self.hotkeys.stop()
        if self.overlay is not None:
            self.overlay.close()
        if self._hidden:
            self._unhide()
        if self.settings["restore_on_exit"] and self.backend.supports_native:
            try:
                self.backend.restore_default(previous=True)
            except Exception:  # noqa: BLE001
                log.exception("restore on exit failed")
        self.settings.save()

    def _emergency_restore(self) -> None:
        if self._hidden:
            self._unhide()

    # -------------------------------------------------------------- skins & size
    @property
    def skin(self) -> Skin | None:
        return self.library.get(self.active_skin_id or self.settings["skin"])

    def adjustments(self, skin_id: str) -> Adjustments:
        return Adjustments.from_dict(self.settings.adjustments_for(skin_id))

    def set_adjustments(self, skin_id: str, adj: Adjustments, apply: bool = True) -> None:
        self.settings.set_adjustments(skin_id, adj.to_dict())
        self.settings.save()
        if apply and skin_id == self.active_skin_id:
            self.apply_skin(skin_id, persist=False)

    def size(self) -> int:
        if self.override_rule and self.override_rule.get("size"):
            return int(self.override_rule["size"])
        return int(self.settings["size"])

    def set_size(self, size: int) -> None:
        self.settings["size"] = int(max(16, min(256, size)))
        self.settings.save()
        self.settings_changed.emit()
        if self.active_skin_id:
            self.apply_skin(self.active_skin_id, persist=False)

    def apply_skin(self, skin_id: str, persist: bool = True) -> None:
        """Apply a skin (rendering happens on a worker thread)."""
        skin = self.library.get(skin_id)
        if skin is None:
            self.status.emit(f"Skin not found: {skin_id}")
            fallback = next(iter(self.library), None)
            if fallback is None:
                return
            skin, skin_id = fallback, fallback.id
        if persist:
            self.settings["skin"] = skin_id
            self.settings.push_recent(skin_id)
            self.settings.save()
        self.active_skin_id = skin_id
        adj = self.adjustments(skin_id)
        size = self.size()
        if self.overlay is not None:
            self.overlay.set_cursor_skin(skin, size, adj)
        self.skin_changed.emit(skin_id)
        if self.settings["effects"].get("overlay_cursor") and self._hidden:
            self.status.emit(f"Overlay cursor: {skin.name}")
            return
        if not self.backend.supports_native:
            self.status.emit(self.backend.notes)
            return
        with self._apply_lock:
            self._pending = (skin, size, adj)
            if self._applying:
                return
            self._applying = True
        self.busy_changed.emit(True)
        threading.Thread(target=self._apply_worker, name="mouze-apply", daemon=True).start()

    def _apply_worker(self) -> None:
        while True:
            with self._apply_lock:
                job, self._pending = self._pending, None
                if job is None:
                    self._applying = False
                    break
            skin, size, adj = job
            try:
                msg, ok = self.backend.apply(skin, size, adj), True
            except BackendError as exc:
                msg, ok = str(exc), False
            except Exception as exc:  # noqa: BLE001
                log.exception("apply failed")
                msg, ok = f"Could not apply cursor: {exc}", False
            self._apply_done.emit(skin.id, msg, ok)
        self._apply_idle.emit()

    def _on_apply_done(self, skin_id: str, message: str, ok: bool) -> None:
        self.status.emit(message)

    def restore_default(self, previous: bool = True) -> None:
        self.settings["effects"]["overlay_cursor"] = False
        if self._hidden:
            self._hidden = False
            self.settings["cursor_hidden"] = False
        try:
            msg = self.backend.restore_default(previous=previous)
        except Exception as exc:  # noqa: BLE001
            msg = f"Restore failed: {exc}"
        self.settings.save()
        self.status.emit(msg)

    def _safe_restore(self) -> None:
        try:
            self.backend.restore_default(previous=True)
        except Exception:  # noqa: BLE001
            log.exception("restore failed")

    def cycle(self, step: int) -> None:
        pool = [i for i in self.settings["favorites"] if i in self.library]
        if len(pool) < 2:
            pool = [s.id for s in self.library]
        cur = self.active_skin_id
        idx = pool.index(cur) if cur in pool else -1
        self.apply_skin(pool[(idx + step) % len(pool)])

    def step_size(self, direction: int) -> None:
        cur = int(self.settings["size"])
        if direction > 0:
            nxt = next((s for s in SIZES if s > cur), SIZES[-1])
        else:
            nxt = next((s for s in reversed(SIZES) if s < cur), SIZES[0])
        self.set_size(nxt)
        self.status.emit(f"Cursor size {nxt}px")

    # ------------------------------------------------------------------- effects
    def effects_cfg(self) -> dict:
        return self.settings["effects"]

    def refresh_effects(self) -> None:
        cfg = self.effects_cfg()
        want = bool(cfg.get("enabled"))
        if want:
            self._ensure_overlay()
            self.overlay.configure(cfg)
            self.overlay.start()
        elif self.overlay is not None and not self._locator_timer.isActive():
            self.overlay.stop()
        self._sync_overlay_cursor()
        self.effects_changed.emit(want)

    def set_effects_enabled(self, enabled: bool) -> None:
        self.settings["effects"]["enabled"] = bool(enabled)
        self.settings.save()
        self.refresh_effects()
        self.status.emit("Effects on" if enabled else "Effects off")

    def _ensure_overlay(self):
        if self.overlay is None:
            from .overlay.window import OverlayManager
            self.overlay = OverlayManager(self.effects_cfg(), self.backend, self)
            skin = self.skin
            if skin is not None:
                self.overlay.set_cursor_skin(skin, self.size(), self.adjustments(skin.id))
        return self.overlay

    def _sync_overlay_cursor(self) -> None:
        cfg = self.effects_cfg()
        want = bool(cfg.get("enabled") and cfg.get("overlay_cursor"))
        can = getattr(self.backend, "supports_role_detection", False)
        if want and can and not self._hidden:
            try:
                self.backend.hide()
                self._hidden = True
                self.settings["cursor_hidden"] = True
                self.settings.save()
            except Exception as exc:  # noqa: BLE001
                self.status.emit(f"Overlay cursor unavailable: {exc}")
        elif not want and self._hidden:
            self._unhide()

    def _unhide(self) -> None:
        self._hidden = False
        self.settings["cursor_hidden"] = False
        self.settings.save()
        skin = self.skin
        if skin is not None and self.backend.supports_native:
            try:
                self.backend.apply(skin, self.size(), self.adjustments(skin.id))
                return
            except Exception:  # noqa: BLE001
                log.exception("re-apply after overlay cursor failed")
        self._safe_restore()

    def locate(self) -> None:
        self._ensure_overlay()
        if not self.overlay.running:
            self.overlay.configure(self.effects_cfg())
            self.overlay.start()
            self._locator_timer.start(1600)
        self.overlay.locator.trigger()

    def _maybe_stop_overlay(self) -> None:
        if self.overlay is not None and not self.effects_cfg().get("enabled"):
            self.overlay.stop()

    def toggle_spotlight(self) -> None:
        spot = self.effects_cfg()["spotlight"]
        spot["enabled"] = not spot.get("enabled")
        if spot["enabled"] and not self.effects_cfg().get("enabled"):
            self.effects_cfg()["enabled"] = True
        self.settings.save()
        self.refresh_effects()
        self.settings_changed.emit()

    # ------------------------------------------------------------------- hotkeys
    def refresh_hotkeys(self) -> list[str]:
        if self.settings["hotkeys_enabled"]:
            self.hotkeys.start(self.settings["hotkeys"])
        else:
            self.hotkeys.stop()
        return [f"{a}: {e}" for a, e in self.hotkeys.failed.items()]

    def handle_action(self, action: str) -> None:
        if action == "toggle_effects":
            self.set_effects_enabled(not self.effects_cfg().get("enabled"))
        elif action == "next_skin":
            self.cycle(1)
        elif action == "prev_skin":
            self.cycle(-1)
        elif action == "size_up":
            self.step_size(1)
        elif action == "size_down":
            self.step_size(-1)
        elif action == "restore_default":
            self.restore_default(previous=True)
        elif action == "locate":
            self.locate()
        elif action == "spotlight":
            self.toggle_spotlight()
        elif action == "show_window":
            self.show_window_requested.emit()

    # --------------------------------------------------- profiles / auto-pause
    def _watch(self) -> None:
        cfg = self.settings
        need_fg = (cfg["profiles"]["enabled"] and cfg["profiles"]["rules"]) or (
            self.overlay is not None and self.overlay.running and cfg["effects"].get("pause_fullscreen"))
        info = foreground.foreground() if need_fg else None
        self.last_foreground = info
        if self.overlay is not None and self.overlay.running:
            self.overlay.set_paused(bool(info and info.fullscreen and cfg["effects"].get("pause_fullscreen")))
        if cfg["profiles"]["enabled"]:
            self.evaluate_profiles(info.process if info else None)

    def evaluate_profiles(self, process: str | None, now: dt.time | None = None) -> dict | None:
        rules = self.settings["profiles"]["rules"]
        match = next((r for r in rules if rule_matches(r, process, now)), None)
        if match == self.override_rule:
            return match
        self.override_rule = match
        target = (match.get("skin") if match else None) or self.settings["skin"]
        effects = (match or {}).get("effects", "keep")
        if effects in ("on", "off"):
            if self._effects_before is None:
                self._effects_before = bool(self.effects_cfg().get("enabled"))
            self.effects_cfg()["enabled"] = effects == "on"
            self.refresh_effects()
        elif self._effects_before is not None:
            self.effects_cfg()["enabled"] = self._effects_before
            self._effects_before = None
            self.refresh_effects()
        self.apply_skin(target, persist=False)
        label = (match.get("name") or match.get("process") or match.get("time")) if match else None
        self.status.emit(f"Profile: {label}" if match else "Profile ended")
        return match

    # -------------------------------------------------------------------- shuffle
    def refresh_shuffle(self) -> None:
        sh = self.settings["shuffle"]
        if sh.get("enabled"):
            self.shuffle_timer.start(max(1, int(sh.get("minutes", 30))) * 60_000)
        else:
            self.shuffle_timer.stop()

    def shuffle_now(self) -> None:
        sh = self.settings["shuffle"]
        pool = self.settings["favorites"] if sh.get("favorites_only") and self.settings["favorites"] else None
        skin = self.library.random(pool, exclude=self.active_skin_id)
        if skin:
            self.apply_skin(skin.id)
