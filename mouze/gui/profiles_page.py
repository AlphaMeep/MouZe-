"""Profiles page: per-app / time-of-day rules and the skin shuffler."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..controller import SIZES
from ..system import foreground

EFFECT_CHOICES = [("keep", "Leave as is"), ("on", "Turn on"), ("off", "Turn off")]


class RuleDialog(QDialog):
    def __init__(self, controller, rule: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Profile rule")
        self.c = controller
        rule = dict(rule or {})
        form = QFormLayout(self)
        self.name = QLineEdit(rule.get("name", ""))
        self.name.setPlaceholderText("e.g. Gaming")
        self.process = QLineEdit(rule.get("process", ""))
        self.process.setPlaceholderText("game.exe, *valorant*, code   (comma separated, wildcards ok)")
        detect = QPushButton("Use the app in front in 3 s")
        detect.clicked.connect(self._detect)
        prow = QHBoxLayout()
        prow.addWidget(self.process, 1)
        prow.addWidget(detect)
        self.time = QLineEdit(rule.get("time", ""))
        self.time.setPlaceholderText("optional, e.g. 19:00-07:00")
        self.skin = QComboBox()
        self.skin.addItem("(keep main skin)", "")
        for s in sorted(self.c.library, key=lambda s: s.name.lower()):
            self.skin.addItem(f"{s.name}  [{s.meta.category}]", s.id)
        idx = self.skin.findData(rule.get("skin", ""))
        self.skin.setCurrentIndex(max(0, idx))
        self.size = QComboBox()
        self.size.addItem("(keep size)", 0)
        for s in SIZES:
            self.size.addItem(f"{s} px", s)
        self.size.setCurrentIndex(max(0, self.size.findData(int(rule.get("size") or 0))))
        self.effects = QComboBox()
        for k, v in EFFECT_CHOICES:
            self.effects.addItem(v, k)
        self.effects.setCurrentIndex(max(0, self.effects.findData(rule.get("effects", "keep"))))
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(rule.get("enabled", True))
        form.addRow("Name", self.name)
        form.addRow("Apps", prow)
        form.addRow("Time window", self.time)
        form.addRow("Skin", self.skin)
        form.addRow("Size", self.size)
        form.addRow("Effects", self.effects)
        form.addRow(self.enabled)
        hint = QLabel("A rule needs apps, a time window, or both. The first matching rule wins.")
        hint.setProperty("dim", True)
        form.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.resize(560, 0)

    def _detect(self):
        self.process.setPlaceholderText("switch to the app now…")
        QTimer.singleShot(3000, self._grab)

    def _grab(self):
        info = foreground.foreground()
        if info and info.process:
            existing = [p.strip() for p in self.process.text().split(",") if p.strip()]
            if info.process not in existing:
                existing.append(info.process)
            self.process.setText(", ".join(existing))
        self.raise_()
        self.activateWindow()

    def rule(self) -> dict:
        return {"name": self.name.text().strip(), "process": self.process.text().strip(),
                "time": self.time.text().strip(), "skin": self.skin.currentData(),
                "size": int(self.size.currentData() or 0), "effects": self.effects.currentData(),
                "enabled": self.enabled.isChecked()}


class ProfilesPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 16)
        t = QLabel("Profiles")
        t.setObjectName("title")
        lay.addWidget(t)
        info = QLabel("Switch skins automatically for specific apps or games, or by time of day "
                      "(e.g. a dark skin at night). When no rule matches, your main skin is used.")
        info.setWordWrap(True)
        info.setProperty("dim", True)
        lay.addWidget(info)

        self.enabled = QCheckBox("Enable automatic profiles")
        self.enabled.setChecked(self.c.settings["profiles"]["enabled"])
        self.enabled.toggled.connect(self._toggle)
        lay.addWidget(self.enabled)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Name", "Apps", "Time", "Skin", "Size", "Effects"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(lambda _: self.edit())
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        for label, fn in (("Add rule", self.add), ("Edit", self.edit), ("Remove", self.remove),
                          ("Move up", lambda: self.move(-1)), ("Move down", lambda: self.move(1))):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        self.fg_label = QLabel()
        self.fg_label.setProperty("dim", True)
        row.addWidget(self.fg_label)
        lay.addLayout(row)

        sh = QGroupBox("Skin shuffle")
        f = QFormLayout(sh)
        cfg = self.c.settings["shuffle"]
        self.sh_on = QCheckBox("Switch to a random skin every")
        self.sh_on.setChecked(cfg["enabled"])
        self.sh_minutes = QSpinBox()
        self.sh_minutes.setRange(1, 24 * 60)
        self.sh_minutes.setSuffix(" min")
        self.sh_minutes.setValue(int(cfg["minutes"]))
        srow = QHBoxLayout()
        srow.addWidget(self.sh_on)
        srow.addWidget(self.sh_minutes)
        srow.addStretch(1)
        self.sh_favs = QCheckBox("Only pick from favourites")
        self.sh_favs.setChecked(cfg["favorites_only"])
        now = QPushButton("Shuffle now")
        now.clicked.connect(self.c.shuffle_now)
        f.addRow(srow)
        f.addRow(self.sh_favs)
        f.addRow(now)
        for w in (self.sh_on, self.sh_favs):
            w.toggled.connect(self._save_shuffle)
        self.sh_minutes.valueChanged.connect(self._save_shuffle)
        lay.addWidget(sh)

        self.fg_timer = QTimer(self)
        self.fg_timer.timeout.connect(self._show_fg)
        self.fg_timer.start(2000)
        self.refresh()

    def rules(self) -> list[dict]:
        return self.c.settings["profiles"]["rules"]

    def refresh(self):
        self.table.setRowCount(0)
        effects = dict(EFFECT_CHOICES)
        for r in self.rules():
            i = self.table.rowCount()
            self.table.insertRow(i)
            skin = self.c.library.get(r.get("skin") or "")
            vals = [r.get("name") or "-", r.get("process") or "any", r.get("time") or "any time",
                    skin.name if skin else "(main skin)", f"{r['size']} px" if r.get("size") else "-",
                    effects.get(r.get("effects", "keep"), "-")]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if not r.get("enabled", True):
                    item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(i, j, item)

    def _save(self):
        self.c.settings.save()
        self.refresh()
        self.c.override_rule = None
        self.c.evaluate_profiles(self.c.last_foreground.process if self.c.last_foreground else None)

    def add(self):
        d = RuleDialog(self.c, parent=self)
        if d.exec():
            self.rules().append(d.rule())
            self._save()

    def edit(self):
        i = self.table.currentRow()
        if i < 0:
            return
        d = RuleDialog(self.c, self.rules()[i], parent=self)
        if d.exec():
            self.rules()[i] = d.rule()
            self._save()

    def remove(self):
        i = self.table.currentRow()
        if i >= 0:
            del self.rules()[i]
            self._save()

    def move(self, step: int):
        i = self.table.currentRow()
        j = i + step
        rules = self.rules()
        if 0 <= i < len(rules) and 0 <= j < len(rules):
            rules[i], rules[j] = rules[j], rules[i]
            self._save()
            self.table.selectRow(j)

    def _toggle(self, on: bool):
        self.c.settings["profiles"]["enabled"] = on
        self.c.settings.save()
        if not on and self.c.override_rule:
            self.c.override_rule = None
            self.c.apply_skin(self.c.settings["skin"], persist=False)

    def _save_shuffle(self, *_):
        sh = self.c.settings["shuffle"]
        sh.update(enabled=self.sh_on.isChecked(), minutes=self.sh_minutes.value(),
                  favorites_only=self.sh_favs.isChecked())
        self.c.settings.save()
        self.c.refresh_shuffle()

    def _show_fg(self):
        if not self.isVisible():
            return
        info = self.c.last_foreground or foreground.foreground()
        rule = self.c.override_rule
        text = f"Front app: {info.process}" if info and info.process else "Front app: unknown"
        if rule:
            text += f"  ·  active rule: {rule.get('name') or rule.get('process') or rule.get('time')}"
        self.fg_label.setText(text)
