"""Settings page: startup behaviour, hotkeys, system cursors, about."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, paths
from ..config import DEFAULT_HOTKEYS, HOTKEY_LABELS
from ..i18n import LANGUAGES, tr
from ..system import autostart
from .library_page import _open_folder

QT_KEY_NAMES = {"pgup": "pageup", "pgdown": "pagedown", "meta": "win", "return": "enter", "del": "delete",
                "ins": "insert", "+": "plus", "-": "minus"}


def seq_to_hotkey(seq: QKeySequence) -> str:
    text = seq.toString(QKeySequence.SequenceFormat.PortableText).split(",")[0].strip()
    if not text:
        return ""
    parts = []
    for part in text.replace("++", "+plus").split("+"):
        p = part.strip().lower()
        parts.append(QT_KEY_NAMES.get(p, p))
    return "+".join(p for p in parts if p)


def hotkey_to_seq(text: str) -> QKeySequence:
    if not text:
        return QKeySequence()
    rev = {"pageup": "PgUp", "pagedown": "PgDown", "win": "Meta", "enter": "Return", "plus": "+",
           "minus": "-", "delete": "Del", "insert": "Ins", "esc": "Esc", "escape": "Esc"}
    parts = [rev.get(p, p.capitalize() if len(p) > 1 else p.upper()) for p in text.split("+")]
    return QKeySequence("+".join(parts))


class SettingsPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 12, 16, 16)
        t = QLabel(tr("Settings"))
        t.setObjectName("title")
        lay.addWidget(t)
        s = self.c.settings

        g = QGroupBox(tr("General"))
        f = QFormLayout(g)
        self.autostart = QCheckBox(tr("Start MouZe when I log in"))
        try:
            self.autostart.setChecked(autostart.is_enabled())
        except Exception:  # noqa: BLE001
            self.autostart.setEnabled(False)
        self.autostart.toggled.connect(self._autostart)
        self.apply_start = QCheckBox(tr("Re-apply my skin when MouZe starts"))
        self.apply_start.setChecked(s["apply_on_start"])
        self.start_min = QCheckBox(tr("Start minimised to the system tray"))
        self.start_min.setChecked(s["start_minimized"])
        self.min_tray = QCheckBox(tr("Closing the window keeps MouZe running in the tray"))
        self.min_tray.setChecked(s["minimize_to_tray"])
        self.restore_exit = QCheckBox(tr("Restore my original cursors when MouZe quits"))
        self.restore_exit.setChecked(s["restore_on_exit"])
        self.silent = QCheckBox(tr("Silent running: start hidden in the tray and show no notifications"))
        self.silent.setChecked(s["silent_running"])
        self.auto_update = QCheckBox(tr("Keep subscribed community skins up to date"))
        self.auto_update.setChecked(s["auto_update_subscriptions"])
        self.display_refresh = QCheckBox(tr("Re-render cursors when monitors or display scaling change"))
        self.display_refresh.setChecked(s["refresh_on_display_change"])
        for w, key in ((self.apply_start, "apply_on_start"), (self.start_min, "start_minimized"),
                       (self.min_tray, "minimize_to_tray"), (self.restore_exit, "restore_on_exit"),
                       (self.silent, "silent_running"), (self.auto_update, "auto_update_subscriptions"),
                       (self.display_refresh, "refresh_on_display_change")):
            w.toggled.connect(lambda v, k=key: self._set(k, v))
        for w in (self.autostart, self.apply_start, self.start_min, self.min_tray, self.restore_exit, self.silent,
                  self.auto_update, self.display_refresh):
            f.addRow(w)
        self.language = QComboBox()
        self.language.addItem("Automatic (system language)", "auto")
        for code, label in LANGUAGES.items():
            self.language.addItem(label, code)
        self.language.setCurrentIndex(max(0, self.language.findData(s["language"])))
        self.language.currentIndexChanged.connect(self._language)
        restart = QPushButton(tr("Restart MouZe"))
        restart.clicked.connect(self.c.restart)
        lrow = QHBoxLayout()
        lrow.addWidget(self.language, 1)
        lrow.addWidget(restart)
        f.addRow(tr("Language"), lrow)
        note = QLabel(tr("Cursors applied by MouZe stay active even when MouZe is closed - it does not need "
                      "to keep running unless you use effects, hotkeys, profiles or shuffle."))
        note.setWordWrap(True)
        note.setProperty("dim", True)
        f.addRow(note)
        lay.addWidget(g)

        g = QGroupBox(tr("Global hotkeys"))
        f = QFormLayout(g)
        self.hk_on = QCheckBox(tr("Enable global hotkeys"))
        self.hk_on.setChecked(s["hotkeys_enabled"])
        f.addRow(self.hk_on)
        self.hk_edits = {}
        for action, label in HOTKEY_LABELS.items():
            e = QKeySequenceEdit(hotkey_to_seq(s["hotkeys"].get(action, "")))
            e.setMaximumSequenceLength(1) if hasattr(e, "setMaximumSequenceLength") else None
            clear = QPushButton(tr("Clear"))
            clear.clicked.connect(e.clear)
            row = QHBoxLayout()
            row.addWidget(e, 1)
            row.addWidget(clear)
            f.addRow(tr(label), row)
            self.hk_edits[action] = e
        btns = QHBoxLayout()
        save = QPushButton(tr("Save hotkeys"))
        save.setObjectName("primary")
        save.clicked.connect(self._save_hotkeys)
        reset = QPushButton(tr("Reset to defaults"))
        reset.clicked.connect(self._reset_hotkeys)
        btns.addWidget(save)
        btns.addWidget(reset)
        btns.addStretch(1)
        f.addRow(btns)
        self.hk_status = QLabel()
        self.hk_status.setWordWrap(True)
        self.hk_status.setProperty("dim", True)
        f.addRow(self.hk_status)
        if sys.platform != "win32":
            n = QLabel(tr("On Linux/macOS global hotkeys need the optional 'pynput' package "
                       "(pip install mouze[input]). They are not available on Wayland."))
            n.setWordWrap(True)
            n.setProperty("dim", True)
            f.addRow(n)
        lay.addWidget(g)

        g = QGroupBox(tr("System cursors"))
        v = QVBoxLayout(g)
        info = QLabel(f"Backend: {self.c.backend.name}. {self.c.backend.notes}")
        info.setWordWrap(True)
        info.setProperty("dim", True)
        v.addWidget(info)
        row = QHBoxLayout()
        prev = QPushButton(tr("Restore my previous cursors"))
        prev.clicked.connect(lambda: self.c.restore_default(previous=True))
        default = QPushButton(tr("Restore OS default cursors"))
        default.clicked.connect(lambda: self.c.restore_default(previous=False))
        folder = QPushButton(tr("Open skins folder"))
        folder.clicked.connect(lambda: _open_folder(paths.skins_dir()))
        cfg = QPushButton(tr("Open settings folder"))
        cfg.clicked.connect(lambda: _open_folder(paths.config_dir()))
        for b in (prev, default, folder, cfg):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        lay.addWidget(g)

        g = QGroupBox(tr("About"))
        v = QVBoxLayout(g)
        about = QLabel(
            f"<b>MouZe {__version__}</b> - free and open-source custom cursors, cursor effects and a cursor "
            "designer.<br>MIT licensed. Contributions and skins welcome: "
            "<a href='https://github.com/AlphaMeep/MouZe-' style='color:#00d1ff'>github.com/AlphaMeep/MouZe-</a>")
        about.setOpenExternalLinks(True)
        about.setWordWrap(True)
        about.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(about)
        lay.addWidget(g)
        lay.addStretch(1)

    def _language(self, *_):
        self.c.settings["language"] = self.language.currentData()
        self.c.settings.save()
        if QMessageBox.question(self, tr("Language"), tr("Restart MouZe now to switch language?")) \
                == QMessageBox.StandardButton.Yes:
            self.c.restart()

    def _set(self, key, value):
        self.c.settings[key] = value
        self.c.settings.save()

    def _autostart(self, on: bool):
        try:
            autostart.set_enabled(on)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("Autostart"), f"Could not change autostart: {exc}")

    def _save_hotkeys(self):
        hk = {a: seq_to_hotkey(e.keySequence()) for a, e in self.hk_edits.items()}
        self.c.settings["hotkeys"] = hk
        self.c.settings["hotkeys_enabled"] = self.hk_on.isChecked()
        self.c.settings.save()
        failed = self.c.refresh_hotkeys()
        self.hk_status.setText(tr("Hotkeys saved.") if not failed else tr("Some hotkeys could not be registered:")
                               + "\n" + "\n".join(failed))

    def _reset_hotkeys(self):
        for a, e in self.hk_edits.items():
            e.setKeySequence(hotkey_to_seq(DEFAULT_HOTKEYS.get(a, "")))
        self._save_hotkeys()
