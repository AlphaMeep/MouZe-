"""Studio: the procedural Designer and the image-based Pack Builder."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import paths
from ..builtin.procedural import ANIMATED_STYLES, DEFAULT_RECIPE, POINTER_NAMES, STYLES, ProceduralSkin
from ..qtrender import pil_to_qpixmap
from ..roles import Role, guess_role
from ..skin import SUPPORTED_EXTS, CursorSource, SkinMeta, load_source, save_skin, slugify
from .widgets import ColorButton, LabeledSlider, RoleGrid, TestArea, checker_brush


def unique_dir(base: Path) -> Path:
    d, i = base, 2
    while d.exists():
        d = base.with_name(f"{base.name}-{i}")
        i += 1
    return d


class StudioPage(QWidget):
    saved = Signal(str)   # skin id

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 16)
        t = QLabel("Studio")
        t.setObjectName("title")
        lay.addWidget(t)
        self.tabs = QTabWidget()
        self.designer = DesignerTab(self)
        self.builder = PackBuilderTab(self)
        self.tabs.addTab(self.designer, "Designer")
        self.tabs.addTab(self.builder, "Pack Builder")
        lay.addWidget(self.tabs, 1)

    def remix(self, skin_id: str):
        self.tabs.setCurrentWidget(self.designer)
        self.designer.load_from(skin_id)


# ============================================================================ Designer

class DesignerTab(QWidget):
    def __init__(self, studio: StudioPage):
        super().__init__()
        self.studio = studio
        self.c = studio.c
        self.recipe = dict(DEFAULT_RECIPE)
        self._loading = False
        root = QHBoxLayout(self)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMaximumWidth(400)
        left = QWidget()
        left_scroll.setWidget(left)
        form = QFormLayout(left)
        self.name = QLineEdit("My Cursor")
        self.start = QComboBox()
        self.start.addItem("Start from…", "")
        for s in self.c.library:
            if getattr(s, "recipe", None) is not None:
                self.start.addItem(f"{s.name}  [{s.meta.category}]", s.id)
        self.start.currentIndexChanged.connect(lambda _: self.start.currentData() and self.load_from(self.start.currentData()))
        self.pointer = QComboBox()
        for k, v in POINTER_NAMES.items():
            self.pointer.addItem(v, k)
        self.style = QComboBox()
        for k, v in STYLES.items():
            self.style.addItem(v, k)
        self.fill = ColorButton("#ffffff", alpha=True)
        self.outline = ColorButton("#000000", alpha=True)
        self.accent = ColorButton("#1e88e5")
        self.glow = ColorButton("#00e5ff")
        self.g1, self.g2, self.g3 = ColorButton("#ff512f"), ColorButton("#f09819"), ColorButton("#ffffff")
        self.g3_on = QCheckBox("3rd")
        grow = QHBoxLayout()
        for w in (self.g1, self.g2, self.g3, self.g3_on):
            grow.addWidget(w)
        grow.addStretch(1)
        self.width_s = LabeledSlider(0.5, 3.0, 1.5, 0.1, "{:.1f}")
        self.shadow = QCheckBox("Drop shadow")
        self.rainbow = QCheckBox("Rainbow (animated)")
        self.delay = LabeledSlider(20, 200, 50, 5, "{:.0f} ms")
        form.addRow("Name", self.name)
        form.addRow("Template", self.start)
        form.addRow("Pointer shape", self.pointer)
        form.addRow("Style", self.style)
        form.addRow("Fill / tint", self.fill)
        form.addRow("Outline", self.outline)
        form.addRow("Accent", self.accent)
        form.addRow("Glow (neon)", self.glow)
        form.addRow("Gradient", grow)
        form.addRow("Outline width", self.width_s)
        form.addRow(self.shadow)
        form.addRow(self.rainbow)
        form.addRow("Frame delay", self.delay)
        btns = QHBoxLayout()
        save = QPushButton("Save to library")
        save.clicked.connect(lambda: self.save(apply=False))
        apply_btn = QPushButton("Save && apply")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(lambda: self.save(apply=True))
        btns.addWidget(save)
        btns.addWidget(apply_btn)
        form.addRow(btns)
        root.addWidget(left_scroll)

        right = QVBoxLayout()
        bg = QHBoxLayout()
        bg.addWidget(QLabel("Preview background"))
        self.bg = QComboBox()
        self.bg.addItems(["dark", "light", "checker"])
        bg.addWidget(self.bg)
        bg.addStretch(1)
        right.addLayout(bg)
        self.grid = RoleGrid(box=68, columns=6)
        self.bg.currentTextChanged.connect(self.grid.set_background)
        right.addWidget(self.grid)
        self.test = TestArea()
        right.addWidget(self.test)
        right.addStretch(1)
        root.addLayout(right, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._preview)
        for w in (self.pointer, self.style):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.fill, self.outline, self.accent, self.glow, self.g1, self.g2, self.g3):
            w.colorChanged.connect(self._changed)
        for w in (self.shadow, self.rainbow, self.g3_on):
            w.toggled.connect(self._changed)
        self.width_s.valueChanged.connect(self._changed)
        self.delay.valueChanged.connect(self._changed)
        self.set_recipe(self.recipe)

    def set_recipe(self, r: dict):
        r = {**DEFAULT_RECIPE, **r}
        self._loading = True
        self.pointer.setCurrentIndex(max(0, self.pointer.findData(r["pointer"])))
        self.style.setCurrentIndex(max(0, self.style.findData(r["style"])))
        self.fill.set_color(r["fill"])
        self.outline.set_color(r["outline"])
        self.accent.set_color(r["accent"])
        self.glow.set_color(r["glow"])
        grad = list(r["gradient"]) + ["#ffffff"] * 3
        self.g1.set_color(grad[0])
        self.g2.set_color(grad[1])
        self.g3.set_color(grad[2])
        self.g3_on.setChecked(len(r["gradient"]) >= 3)
        self.width_s.set_value(float(r["outline_width"]))
        self.shadow.setChecked(bool(r["shadow"]))
        self.rainbow.setChecked(bool(r["rainbow"]))
        self.delay.set_value(int(r["frame_delay"]))
        self._loading = False
        self._preview()

    def current_recipe(self) -> dict:
        grad = [self.g1.color(), self.g2.color()] + ([self.g3.color()] if self.g3_on.isChecked() else [])
        return {"pointer": self.pointer.currentData(), "style": self.style.currentData(),
                "fill": self.fill.color(), "outline": self.outline.color(), "accent": self.accent.color(),
                "glow": self.glow.color(), "gradient": grad, "outline_width": round(self.width_s.value(), 2),
                "shadow": self.shadow.isChecked(), "rainbow": self.rainbow.isChecked(),
                "frame_delay": int(self.delay.value())}

    def load_from(self, skin_id: str):
        skin = self.c.library.get(skin_id)
        if skin is None or getattr(skin, "recipe", None) is None:
            return
        self.name.setText(f"{skin.name} Remix")
        self.set_recipe(skin.recipe)

    def _changed(self, *_):
        if not self._loading:
            self._timer.start()

    def _skin(self) -> ProceduralSkin:
        meta = SkinMeta(name=self.name.text().strip() or "My Cursor", author="You", category="Custom",
                        tags=["custom"] + (["animated"] if self.style.currentData() in ANIMATED_STYLES else []))
        return ProceduralSkin("designer:preview", meta, self.current_recipe())

    def _preview(self):
        skin = self._skin()
        self.grid.set_skin(skin, 48)
        self.test.set_skin(skin, int(self.c.settings["size"]), None)

    def save(self, apply: bool):
        skin = self._skin()
        dest = unique_dir(paths.skins_dir() / slugify(skin.name))
        save_skin(skin, dest, size=64)
        new = self.c.library.add_from_path(dest)
        self.studio.saved.emit(new.id)
        if apply:
            self.c.apply_skin(new.id)
        self.c.status.emit(f"Saved '{new.name}' to your library")


# ========================================================================= Pack builder

class HotspotEditor(QWidget):
    hotspotChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.pixmap = None
        self.hotspot = (0, 0)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_image(self, pil_img, hotspot):
        self.pixmap = pil_to_qpixmap(pil_img) if pil_img is not None else None
        self.hotspot = tuple(int(v) for v in hotspot)
        self.update()

    def _geometry(self):
        if self.pixmap is None:
            return None
        w, h = self.pixmap.width(), self.pixmap.height()
        scale = min((self.width() - 10) / w, (self.height() - 10) / h)
        if scale >= 1:
            scale = int(scale)
        ox = (self.width() - w * scale) / 2
        oy = (self.height() - h * scale) / 2
        return ox, oy, scale, w, h

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1a1a23"))
        g = self._geometry()
        if g is None:
            p.setPen(QColor("#9a9ab0"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Choose an image for this role")
            return
        ox, oy, scale, w, h = g
        target = QRectF(ox, oy, w * scale, h * scale)
        p.fillRect(target, checker_brush(max(4, int(scale * 2))))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, scale < 1)
        p.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        if scale >= 6:
            p.setPen(QPen(QColor(0, 0, 0, 40), 1))
            for i in range(w + 1):
                p.drawLine(QPointF(ox + i * scale, oy), QPointF(ox + i * scale, oy + h * scale))
            for j in range(h + 1):
                p.drawLine(QPointF(ox, oy + j * scale), QPointF(ox + w * scale, oy + j * scale))
        hx, hy = self.hotspot
        cx, cy = ox + (hx + 0.5) * scale, oy + (hy + 0.5) * scale
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#ff3b6b"), 2))
        p.drawEllipse(QPointF(cx, cy), max(4, scale / 2 + 2), max(4, scale / 2 + 2))
        p.drawLine(QPointF(cx - 12, cy), QPointF(cx - 5, cy))
        p.drawLine(QPointF(cx + 5, cy), QPointF(cx + 12, cy))
        p.drawLine(QPointF(cx, cy - 12), QPointF(cx, cy - 5))
        p.drawLine(QPointF(cx, cy + 5), QPointF(cx, cy + 12))

    def mousePressEvent(self, e):  # noqa: N802
        g = self._geometry()
        if g is None:
            return
        ox, oy, scale, w, h = g
        x = int((e.position().x() - ox) / scale)
        y = int((e.position().y() - oy) / scale)
        if 0 <= x < w and 0 <= y < h:
            self.hotspot = (x, y)
            self.update()
            self.hotspotChanged.emit(x, y)


class PackBuilderTab(QWidget):
    """Assemble a skin from your own images, one per role."""

    def __init__(self, studio: StudioPage):
        super().__init__()
        self.studio = studio
        self.c = studio.c
        self.entries: dict[Role, dict] = {}   # role -> {"path", "hotspot", "delay", "frames", "pixel_art"}
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        meta = QFormLayout()
        self.name = QLineEdit("My Pack")
        self.author = QLineEdit("You")
        meta.addRow("Name", self.name)
        meta.addRow("Author", self.author)
        left.addLayout(meta)
        self.roles = QListWidget()
        for role in Role:
            it = QListWidgetItem(role.label)
            it.setData(Qt.ItemDataRole.UserRole, role.value)
            self.roles.addItem(it)
        self.roles.currentRowChanged.connect(self._select)
        left.addWidget(self.roles, 1)
        auto = QPushButton("Auto-fill from a folder…")
        auto.clicked.connect(self.autofill)
        left.addWidget(auto)
        save = QPushButton("Save to library")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        left.addWidget(save)
        root.addLayout(left)

        right = QVBoxLayout()
        row = QHBoxLayout()
        self.file_label = QLabel("No image")
        self.file_label.setProperty("dim", True)
        choose = QPushButton("Choose image…")
        choose.clicked.connect(self.choose)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear)
        row.addWidget(choose)
        row.addWidget(clear)
        row.addWidget(self.file_label, 1)
        right.addLayout(row)
        self.editor = HotspotEditor()
        self.editor.hotspotChanged.connect(self._hotspot_clicked)
        right.addWidget(self.editor, 1)
        opts = QGroupBox("Options for this role")
        f = QFormLayout(opts)
        self.hx = QSpinBox()
        self.hy = QSpinBox()
        for s in (self.hx, self.hy):
            s.setRange(0, 1024)
            s.valueChanged.connect(self._hotspot_spin)
        hrow = QHBoxLayout()
        hrow.addWidget(QLabel("x"))
        hrow.addWidget(self.hx)
        hrow.addWidget(QLabel("y"))
        hrow.addWidget(self.hy)
        hrow.addStretch(1)
        self.frames = QSpinBox()
        self.frames.setRange(1, 256)
        self.frames.setToolTip("For sprite strips: how many frames are in the image")
        self.delay = QSpinBox()
        self.delay.setRange(0, 2000)
        self.delay.setSuffix(" ms")
        self.delay.setSpecialValueText("from file")
        self.pixel = QCheckBox("Pixel art (scale without smoothing)")
        f.addRow("Hotspot (click the image)", hrow)
        f.addRow("Frames in strip", self.frames)
        f.addRow("Frame delay", self.delay)
        f.addRow(self.pixel)
        self.frames.valueChanged.connect(self._opts)
        self.delay.valueChanged.connect(self._opts)
        self.pixel.toggled.connect(self._opts)
        right.addWidget(opts)
        root.addLayout(right, 1)
        self.roles.setCurrentRow(0)

    def role(self) -> Role:
        return Role(self.roles.currentItem().data(Qt.ItemDataRole.UserRole))

    def _spec(self, e: dict) -> dict:
        spec = {"hotspot": list(e["hotspot"])}
        if e.get("frames", 1) > 1:
            spec["frames"] = e["frames"]
        if e.get("delay"):
            spec["delay"] = e["delay"]
        if e.get("pixel_art"):
            spec["pixel_art"] = True
        return spec

    def _source(self, e: dict) -> CursorSource:
        p = Path(e["path"])
        spec = self._spec(e)
        if not e.get("hotspot_set"):
            spec.pop("hotspot")
        return load_source(p.read_bytes(), p.suffix, spec)

    def _select(self, _row):
        if self.roles.currentItem() is None:
            return
        e = self.entries.get(self.role())
        for w in (self.hx, self.hy, self.frames, self.delay, self.pixel):
            w.blockSignals(True)
        if e is None:
            self.file_label.setText("No image - this role will fall back to a similar one")
            self.editor.set_image(None, (0, 0))
            self.hx.setValue(0)
            self.hy.setValue(0)
            self.frames.setValue(1)
            self.delay.setValue(0)
            self.pixel.setChecked(False)
        else:
            self.file_label.setText(Path(e["path"]).name)
            self.hx.setValue(e["hotspot"][0])
            self.hy.setValue(e["hotspot"][1])
            self.frames.setValue(e.get("frames", 1))
            self.delay.setValue(e.get("delay", 0))
            self.pixel.setChecked(e.get("pixel_art", False))
            self._show(e)
        for w in (self.hx, self.hy, self.frames, self.delay, self.pixel):
            w.blockSignals(False)

    def _show(self, e: dict):
        try:
            src = self._source(e)
            if src.svg is not None:
                img = src.render(src.nominal).frames[0]
            else:
                img = src.frames[0]
            self.editor.set_image(img, e["hotspot"])
            self._set_icon(self.role(), img)
        except Exception as exc:  # noqa: BLE001
            self.editor.set_image(None, (0, 0))
            self.file_label.setText(f"Could not read image: {exc}")

    def _set_icon(self, role: Role, img):
        for i in range(self.roles.count()):
            it = self.roles.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == role.value:
                it.setIcon(QIcon(pil_to_qpixmap(img.resize((24, 24)) if img.width > 24 else img)))

    def _load_entry(self, role: Role, path: Path) -> dict:
        e = {"path": str(path), "hotspot": (0, 0), "frames": 1, "delay": 0, "pixel_art": False}
        src = load_source(path.read_bytes(), path.suffix)
        e["hotspot"] = tuple(int(v) for v in src.hotspot)
        e["hotspot_set"] = path.suffix.lower() in (".cur", ".ani")
        return e

    def choose(self):
        f, _ = QFileDialog.getOpenFileName(
            self, f"Image for {self.role().label}", str(Path.home()),
            "Images & cursors (*.png *.gif *.apng *.webp *.avif *.svg *.cur *.ani *.ico *.bmp)")
        if not f:
            return
        try:
            self.entries[self.role()] = self._load_entry(self.role(), Path(f))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Can't use this file", str(exc))
            return
        self._select(self.roles.currentRow())

    def clear(self):
        self.entries.pop(self.role(), None)
        self.roles.currentItem().setIcon(QIcon())
        self._select(self.roles.currentRow())

    def autofill(self):
        d = QFileDialog.getExistingDirectory(self, "Folder with cursor images", str(Path.home()))
        if not d:
            return
        n = 0
        for f in sorted(Path(d).iterdir()):
            if f.suffix.lower() not in SUPPORTED_EXTS:
                continue
            role = guess_role(f.stem)
            if role and role not in self.entries:
                try:
                    self.entries[role] = self._load_entry(role, f)
                    n += 1
                except Exception:  # noqa: BLE001
                    continue
        if not self.name.text().strip() or self.name.text() == "My Pack":
            self.name.setText(Path(d).name)
        self.c.status.emit(f"Matched {n} image(s) to cursor roles by file name")
        for role, e in self.entries.items():
            try:
                src = self._source(e)
                img = src.render(src.nominal).frames[0] if src.svg is not None else src.frames[0]
                self._set_icon(role, img)
            except Exception:  # noqa: BLE001
                pass
        self._select(self.roles.currentRow())

    def _hotspot_clicked(self, x, y):
        e = self.entries.get(self.role())
        if e is None:
            return
        e["hotspot"] = (x, y)
        e["hotspot_set"] = True
        for s, v in ((self.hx, x), (self.hy, y)):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)

    def _hotspot_spin(self, *_):
        e = self.entries.get(self.role())
        if e is None:
            return
        e["hotspot"] = (self.hx.value(), self.hy.value())
        e["hotspot_set"] = True
        self.editor.hotspot = e["hotspot"]
        self.editor.update()

    def _opts(self, *_):
        e = self.entries.get(self.role())
        if e is None:
            return
        e["frames"] = self.frames.value()
        e["delay"] = self.delay.value()
        e["pixel_art"] = self.pixel.isChecked()
        self._show(e)

    def save(self):
        if not self.entries:
            QMessageBox.information(self, "Pack Builder", "Add at least one image first.")
            return
        if Role.ARROW not in self.entries:
            QMessageBox.information(self, "Pack Builder", "Please add an image for 'Normal Select'.")
            return
        name = self.name.text().strip() or "My Pack"
        dest = unique_dir(paths.skins_dir() / slugify(name))
        dest.mkdir(parents=True)
        cursors = {}
        for role, e in self.entries.items():
            src = Path(e["path"])
            fname = f"{role.value}{src.suffix.lower()}"
            shutil.copyfile(src, dest / fname)
            spec = {"file": fname, **self._spec(e)}
            if not e.get("hotspot_set") and src.suffix.lower() in (".cur", ".ani"):
                spec.pop("hotspot")
            cursors[role.value] = spec
        manifest = {"format": 1, "name": name, "author": self.author.text().strip() or "Unknown",
                    "category": "Custom", "tags": ["custom"], "cursors": cursors}
        (dest / "skin.json").write_text(json.dumps(manifest, indent=2), "utf-8")
        try:
            skin = self.c.library.add_from_path(dest)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(dest, ignore_errors=True)
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.studio.saved.emit(skin.id)
        self.c.status.emit(f"Saved '{skin.name}' to your library")

