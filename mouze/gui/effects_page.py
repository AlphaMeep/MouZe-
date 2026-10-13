"""Effects page: trails, click effects, halo, spotlight, locator, overlay cursor."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..overlay.effects import ClickEffect, TrailEffect
from .widgets import ColorButton, LabeledSlider


class EffectsPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        self._loading = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 12, 16, 16)

        t = QLabel("Cursor effects")
        t.setObjectName("title")
        lay.addWidget(t)
        info = QLabel("Effects are drawn on a transparent, click-through overlay. They never touch other apps "
                      "or games, and they pause automatically when a fullscreen app is in front (optional).")
        info.setWordWrap(True)
        info.setProperty("dim", True)
        lay.addWidget(info)

        top = QHBoxLayout()
        self.enabled = QPushButton("Effects off")
        self.enabled.setCheckable(True)
        self.enabled.setMinimumWidth(140)
        self.enabled.toggled.connect(self._toggle)
        top.addWidget(self.enabled)
        self.locate_btn = QPushButton("Locate cursor now")
        self.locate_btn.clicked.connect(self.c.locate)
        top.addWidget(self.locate_btn)
        top.addStretch(1)
        lay.addLayout(top)

        grid = QGridLayout()
        grid.setSpacing(12)
        lay.addLayout(grid)
        cfg = self.c.effects_cfg()

        # trail -----------------------------------------------------------------------
        g = QGroupBox("Trail")
        f = QFormLayout(g)
        self.trail_on = QCheckBox("Enabled")
        self.trail_style = QComboBox()
        for k, v in TrailEffect.STYLES.items():
            self.trail_style.addItem(v, k)
        self.trail_color = ColorButton(cfg["trail"]["color"])
        self.trail_rainbow = QCheckBox("Rainbow")
        crow = QHBoxLayout()
        crow.addWidget(self.trail_color)
        crow.addWidget(self.trail_rainbow)
        crow.addStretch(1)
        self.trail_len = LabeledSlider(4, 60, cfg["trail"]["length"])
        self.trail_width = LabeledSlider(1, 24, cfg["trail"]["width"])
        f.addRow(self.trail_on)
        f.addRow("Style", self.trail_style)
        f.addRow("Colour", crow)
        f.addRow("Length", self.trail_len)
        f.addRow("Width", self.trail_width)
        grid.addWidget(g, 0, 0)

        # clicks ----------------------------------------------------------------------
        g = QGroupBox("Click effects")
        f = QFormLayout(g)
        self.click_on = QCheckBox("Enabled")
        self.click_style = QComboBox()
        for k, v in ClickEffect.STYLES.items():
            self.click_style.addItem(v, k)
        self.click_left = ColorButton(cfg["clicks"]["left"])
        self.click_right = ColorButton(cfg["clicks"]["right"])
        self.click_middle = ColorButton(cfg["clicks"]["middle"])
        crow = QHBoxLayout()
        for lbl, w in (("L", self.click_left), ("R", self.click_right), ("M", self.click_middle)):
            crow.addWidget(QLabel(lbl))
            crow.addWidget(w)
        crow.addStretch(1)
        self.click_size = LabeledSlider(12, 120, cfg["clicks"]["size"])
        self.click_dur = LabeledSlider(150, 1500, cfg["clicks"]["duration"], 10, "{:.0f} ms")
        f.addRow(self.click_on)
        f.addRow("Style", self.click_style)
        f.addRow("Colours", crow)
        f.addRow("Size", self.click_size)
        f.addRow("Duration", self.click_dur)
        note = QLabel("Needs the optional 'pynput' package on Linux/macOS." if sys.platform != "win32" else "")
        note.setProperty("dim", True)
        note.setWordWrap(True)
        if note.text():
            f.addRow(note)
        grid.addWidget(g, 0, 1)

        # halo ------------------------------------------------------------------------
        g = QGroupBox("Highlight halo")
        f = QFormLayout(g)
        self.halo_on = QCheckBox("Enabled - great for tutorials and screen recordings")
        self.halo_color = ColorButton(cfg["halo"]["color"])
        self.halo_radius = LabeledSlider(10, 120, cfg["halo"]["radius"])
        self.halo_opacity = LabeledSlider(0.05, 1, cfg["halo"]["opacity"], 0.05, "{:.0%}")
        f.addRow(self.halo_on)
        f.addRow("Colour", self.halo_color)
        f.addRow("Radius", self.halo_radius)
        f.addRow("Opacity", self.halo_opacity)
        grid.addWidget(g, 1, 0)

        # spotlight -------------------------------------------------------------------
        g = QGroupBox("Spotlight")
        f = QFormLayout(g)
        self.spot_on = QCheckBox("Enabled - dims the screen around the pointer")
        self.spot_radius = LabeledSlider(40, 500, cfg["spotlight"]["radius"])
        self.spot_dim = LabeledSlider(0.1, 0.95, cfg["spotlight"]["dim"], 0.05, "{:.0%}")
        f.addRow(self.spot_on)
        f.addRow("Radius", self.spot_radius)
        f.addRow("Dim", self.spot_dim)
        grid.addWidget(g, 1, 1)

        # locator ---------------------------------------------------------------------
        g = QGroupBox("Find my cursor")
        f = QFormLayout(g)
        self.shake_on = QCheckBox("Shake the mouse to show where the cursor is")
        self.shake_sens = LabeledSlider(1, 7, cfg["locator"]["sensitivity"])
        self.locator_color = ColorButton(cfg["locator"]["color"])
        f.addRow(self.shake_on)
        f.addRow("Sensitivity", self.shake_sens)
        f.addRow("Colour", self.locator_color)
        grid.addWidget(g, 2, 0)

        # performance -----------------------------------------------------------------
        g = QGroupBox("Performance && overlay cursor")
        f = QFormLayout(g)
        self.fps = QSpinBox()
        self.fps.setRange(15, 240)
        self.fps.setSuffix(" fps")
        self.pause_full = QCheckBox("Pause effects while a fullscreen app/game is focused")
        self.overlay_cursor = QCheckBox("Draw the cursor on the overlay (experimental)")
        self.overlay_cursor.setToolTip(
            "Hides the Windows cursor and draws the skin yourself: any size, smooth animation and tilt.\n"
            "Adds about one frame of latency - keep it off for competitive games.\n"
            "Press the 'restore system cursors' hotkey if anything goes wrong.")
        self.tilt = QCheckBox("Tilt the cursor while moving")
        supported = getattr(self.c.backend, "supports_role_detection", False)
        self.overlay_cursor.setEnabled(supported)
        self.tilt.setEnabled(supported)
        f.addRow("Frame rate", self.fps)
        f.addRow(self.pause_full)
        f.addRow(self.overlay_cursor)
        f.addRow(self.tilt)
        if not supported:
            n = QLabel("Overlay cursor mode is Windows-only.")
            n.setProperty("dim", True)
            f.addRow(n)
        grid.addWidget(g, 2, 1)
        lay.addStretch(1)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(150)
        self._save_timer.timeout.connect(self._commit)

        self.load()
        for w in (self.trail_on, self.trail_rainbow, self.click_on, self.halo_on, self.spot_on, self.shake_on,
                  self.pause_full, self.overlay_cursor, self.tilt):
            w.toggled.connect(self._changed)
        for w in (self.trail_style, self.click_style):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.trail_len, self.trail_width, self.click_size, self.click_dur, self.halo_radius,
                  self.halo_opacity, self.spot_radius, self.spot_dim, self.shake_sens):
            w.valueChanged.connect(self._changed)
        for w in (self.trail_color, self.click_left, self.click_right, self.click_middle, self.halo_color,
                  self.locator_color):
            w.colorChanged.connect(self._changed)
        self.fps.valueChanged.connect(self._changed)
        self.c.effects_changed.connect(self._sync_enabled)
        self.c.settings_changed.connect(self.load)

    def load(self):
        self._loading = True
        cfg = self.c.effects_cfg()
        self._sync_enabled(cfg.get("enabled", False))
        tr = cfg["trail"]
        self.trail_on.setChecked(tr["enabled"])
        self.trail_style.setCurrentIndex(max(0, self.trail_style.findData(tr["style"])))
        self.trail_color.set_color(tr["color"])
        self.trail_rainbow.setChecked(tr["rainbow"])
        self.trail_len.set_value(tr["length"])
        self.trail_width.set_value(tr["width"])
        cl = cfg["clicks"]
        self.click_on.setChecked(cl["enabled"])
        self.click_style.setCurrentIndex(max(0, self.click_style.findData(cl["style"])))
        self.click_left.set_color(cl["left"])
        self.click_right.set_color(cl["right"])
        self.click_middle.set_color(cl["middle"])
        self.click_size.set_value(cl["size"])
        self.click_dur.set_value(cl["duration"])
        h = cfg["halo"]
        self.halo_on.setChecked(h["enabled"])
        self.halo_color.set_color(h["color"])
        self.halo_radius.set_value(h["radius"])
        self.halo_opacity.set_value(h["opacity"])
        s = cfg["spotlight"]
        self.spot_on.setChecked(s["enabled"])
        self.spot_radius.set_value(s["radius"])
        self.spot_dim.set_value(s["dim"])
        lo = cfg["locator"]
        self.shake_on.setChecked(lo["shake"])
        self.shake_sens.set_value(lo["sensitivity"])
        self.locator_color.set_color(lo["color"])
        self.fps.setValue(int(cfg.get("fps", 120)))
        self.pause_full.setChecked(cfg.get("pause_fullscreen", True))
        self.overlay_cursor.setChecked(cfg.get("overlay_cursor", False))
        self.tilt.setChecked(cfg.get("tilt", False))
        self._loading = False

    def _sync_enabled(self, on: bool):
        self.enabled.blockSignals(True)
        self.enabled.setChecked(bool(on))
        self.enabled.setText("Effects on" if on else "Effects off")
        self.enabled.blockSignals(False)

    def _toggle(self, on: bool):
        self.c.set_effects_enabled(on)

    def _changed(self, *_):
        if not self._loading:
            self._save_timer.start()

    def _commit(self):
        cfg = self.c.effects_cfg()
        cfg["trail"].update(enabled=self.trail_on.isChecked(), style=self.trail_style.currentData(),
                            color=self.trail_color.color(), rainbow=self.trail_rainbow.isChecked(),
                            length=int(self.trail_len.value()), width=int(self.trail_width.value()))
        cfg["clicks"].update(enabled=self.click_on.isChecked(), style=self.click_style.currentData(),
                             left=self.click_left.color(), right=self.click_right.color(),
                             middle=self.click_middle.color(), size=int(self.click_size.value()),
                             duration=int(self.click_dur.value()))
        cfg["halo"].update(enabled=self.halo_on.isChecked(), color=self.halo_color.color(),
                           radius=int(self.halo_radius.value()), opacity=round(self.halo_opacity.value(), 2))
        cfg["spotlight"].update(enabled=self.spot_on.isChecked(), radius=int(self.spot_radius.value()),
                                dim=round(self.spot_dim.value(), 2))
        cfg["locator"].update(shake=self.shake_on.isChecked(), sensitivity=int(self.shake_sens.value()),
                              color=self.locator_color.color())
        cfg["fps"] = self.fps.value()
        cfg["pause_fullscreen"] = self.pause_full.isChecked()
        cfg["overlay_cursor"] = self.overlay_cursor.isChecked()
        cfg["tilt"] = self.tilt.isChecked()
        self.c.settings.save()
        self.c.refresh_effects()
