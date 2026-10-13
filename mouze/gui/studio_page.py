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
from ..i18n import tr
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
        t = QLabel(tr("Studio"))
        t.setObjectName("title")
        lay.addWidget(t)
        self.tabs = QTabWidget()
        self.designer = DesignerTab(self)
        self.builder = PackBuilderTab(self)
        self.tabs.addTab(self.designer, tr("Designer"))
        self.tabs.addTab(self.builder, tr("Pack Builder"))
        lay.addWidget(self.tabs, 1)

    def remix(self, skin_id: str):
        self.tabs.setCurrentWidget(self.designer)
        self.designer.load_from(skin_id)

    def edit(self, skin_id: str):
        skin = self.c.library.get(skin_id)
        if skin is None:
            return
        if getattr(skin, "recipe", None) is not None:
            self.remix(skin_id)
            return
        self.tabs.setCurrentWidget(self.builder)
        self.builder.load_existing(skin)


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
            self.pointer.addItem(tr(v), k)
        self.style = QComboBox()
        for k, v in STYLES.items():
            self.style.addItem(tr(v), k)
        self.fill = ColorButton("#ffffff", alpha=True)
        self.outline = ColorButton("#000000", alpha=True)
        self.accent = ColorButton("#1e88e5")
        self.glow = ColorButton("#00e5ff")
        self.g1, self.g2, self.g3 = ColorButton("#ff512f"), ColorButton("#f09819"), ColorButton("#ffffff")
        self.g3_on = QCheckBox(tr("3rd"))
        grow = QHBoxLayout()
        for w in (self.g1, self.g2, self.g3, self.g3_on):
            grow.addWidget(w)
        grow.addStretch(1)
        self.width_s = LabeledSlider(0.5, 3.0, 1.5, 0.1, "{:.1f}")
        self.shadow = QCheckBox(tr("Drop shadow"))
        self.rainbow = QCheckBox(tr("Rainbow (animated)"))
        self.delay = LabeledSlider(20, 200, 50, 5, "{:.0f} ms")
        form.addRow(tr("Name"), self.name)
        form.addRow(tr("Template"), self.start)
        form.addRow(tr("Pointer shape"), self.pointer)
        form.addRow(tr("Style"), self.style)
        form.addRow(tr("Fill / tint"), self.fill)
        form.addRow(tr("Outline"), self.outline)
        form.addRow(tr("Accent"), self.accent)
        form.addRow(tr("Glow (neon)"), self.glow)
        form.addRow(tr("Gradient"), grow)
        form.addRow(tr("Outline width"), self.width_s)
        form.addRow(self.shadow)
        form.addRow(self.rainbow)
        form.addRow(tr("Frame delay"), self.delay)
        btns = QHBoxLayout()
        save = QPushButton(tr("Save to library"))
        save.clicked.connect(lambda: self.save(apply=False))
        apply_btn = QPushButton(tr("Save && apply"))
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(lambda: self.save(apply=True))
        btns.addWidget(save)
        btns.addWidget(apply_btn)
        form.addRow(btns)
        root.addWidget(left_scroll)

        right = QVBoxLayout()
        bg = QHBoxLayout()
        bg.addWidget(QLabel(tr("Preview background")))
        self.bg = QComboBox()
        for key in ("dark", "light", "checker"):
            self.bg.addItem(tr(key.capitalize()), key)
        bg.addWidget(self.bg)
        bg.addStretch(1)
        right.addLayout(bg)
        self.grid = RoleGrid(box=68, columns=6)
        self.bg.currentIndexChanged.connect(lambda _: self.grid.set_background(self.bg.currentData()))
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
        self.name.setText(tr("{name} Remix").format(name=skin.name))
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
        self.c.status.emit(tr("Saved '{name}' to your library").format(name=new.name))


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
        self.editing: Path | None = None       # skin folder being edited in place
        self.editing_manifest: dict = {}
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        meta = QFormLayout()
        self.name = QLineEdit("My Pack")
        self.author = QLineEdit("You")
        meta.addRow(tr("Name"), self.name)
        meta.addRow(tr("Author"), self.author)
        left.addLayout(meta)
        self.roles = QListWidget()
        for role in Role:
            it = QListWidgetItem(role.label)
            it.setData(Qt.ItemDataRole.UserRole, role.value)
            self.roles.addItem(it)
        self.roles.currentRowChanged.connect(self._select)
        left.addWidget(self.roles, 1)
        auto = QPushButton(tr("Auto-fill from a folder…"))
        auto.clicked.connect(self.autofill)
        left.addWidget(auto)
        open_btn = QPushButton(tr("Open existing skin…"))
        open_btn.setToolTip(tr("Edit a skin from your library (imported, Mouse X or Pack Builder skins)"))
        open_btn.clicked.connect(self.open_existing)
        left.addWidget(open_btn)
        new_btn = QPushButton(tr("New pack"))
        new_btn.clicked.connect(self.reset)
        left.addWidget(new_btn)
        self.save_btn = QPushButton(tr("Save to library"))
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self.save)
        left.addWidget(self.save_btn)
        self.save_new_btn = QPushButton(tr("Save as a new skin"))
        self.save_new_btn.clicked.connect(lambda: self.save(as_new=True))
        self.save_new_btn.setVisible(False)
        left.addWidget(self.save_new_btn)
        root.addLayout(left)

        right = QVBoxLayout()
        row = QHBoxLayout()
        self.file_label = QLabel(tr("No image"))
        self.file_label.setProperty("dim", True)
        choose = QPushButton(tr("Choose image…"))
        choose.clicked.connect(self.choose)
        clear = QPushButton(tr("Clear"))
        clear.clicked.connect(self.clear)
        row.addWidget(choose)
        row.addWidget(clear)
        row.addWidget(self.file_label, 1)
        right.addLayout(row)
        self.editor = HotspotEditor()
        self.editor.hotspotChanged.connect(self._hotspot_clicked)
        right.addWidget(self.editor, 1)
        opts = QGroupBox(tr("Options for this role"))
        f = QFormLayout(opts)
        self.hx = QSpinBox()
        self.hy = QSpinBox()
        for s in (self.hx, self.hy):
            s.setRange(0, 1024)
            s.valueChanged.connect(self._hotspot_spin)
        hrow = QHBoxLayout()
        hrow.addWidget(QLabel(tr("x")))
        hrow.addWidget(self.hx)
        hrow.addWidget(QLabel(tr("y")))
        hrow.addWidget(self.hy)
        hrow.addStretch(1)
        self.frames = QSpinBox()
        self.frames.setRange(1, 256)
        self.frames.setToolTip(tr("For sprite strips: how many frames are in the image"))
        self.delay = QSpinBox()
        self.delay.setRange(0, 2000)
        self.delay.setSuffix(" ms")
        self.delay.setSpecialValueText("from file")
        self.pixel = QCheckBox(tr("Pixel art (scale without smoothing)"))
        f.addRow(tr("Hotspot (click the image)"), hrow)
        f.addRow(tr("Frames in strip"), self.frames)
        f.addRow(tr("Frame delay"), self.delay)
        f.addRow(self.pixel)
        self.frames.valueChanged.connect(self._opts)
        self.delay.valueChanged.connect(self._opts)
        self.pixel.toggled.connect(self._opts)
        right.addWidget(opts)
        help_box = QGroupBox(tr("Help"))
        hl = QVBoxLayout(help_box)
        tip = QLabel(
            "1. Pick a role on the left (Normal Select is required).  2. Choose an image: PNG, GIF, APNG, WebP, "
            "AVIF, SVG, CUR or ANI.  3. Click the image to set the hotspot - the exact pixel that clicks.  "
            "4. For sprite strips, set how many frames the image holds.  5. Save.  Roles you leave empty fall back "
            "to a similar cursor.  Tip: name files like busy.gif or link.png and use Auto-fill.")
        tip.setWordWrap(True)
        tip.setProperty("dim", True)
        hl.addWidget(tip)
        right.addWidget(help_box)
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
            self.file_label.setText(tr("No image - this role will fall back to a similar one"))
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
            self.file_label.setText(tr("Could not read image: {error}").format(error=exc))

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
            QMessageBox.warning(self, tr("Can't use this file"), str(exc))
            return
        self._select(self.roles.currentRow())

    def clear(self):
        self.entries.pop(self.role(), None)
        self.roles.currentItem().setIcon(QIcon())
        self._select(self.roles.currentRow())

    def autofill(self):
        d = QFileDialog.getExistingDirectory(self, tr("Folder with cursor images"), str(Path.home()))
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
        self.c.status.emit(tr("Matched {n} image(s) to cursor roles by file name").format(n=n))
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

    # ------------------------------------------------------------ editing existing skins
    def reset(self):
        self.entries.clear()
        self.editing = None
        self.editing_manifest = {}
        self.name.setText(tr("My Pack"))
        self.author.setText(tr("You"))
        for i in range(self.roles.count()):
            self.roles.item(i).setIcon(QIcon())
        self.save_btn.setText(tr("Save to library"))
        self.save_new_btn.setVisible(False)
        self._select(self.roles.currentRow())

    def open_existing(self):
        from PySide6.QtWidgets import QInputDialog
        skins = [s for s in self.c.library if not s.is_builtin and getattr(s, "recipe", None) is None]
        if not skins:
            QMessageBox.information(self, tr("Pack Builder"), tr("There are no imported or image-based skins yet."))
            return
        names = [f"{s.name}  [{s.meta.category}]" for s in skins]
        choice, ok = QInputDialog.getItem(self, tr("Open existing skin"), tr("Skin:"), names, 0, False)
        if ok:
            self.load_existing(skins[names.index(choice)])

    def load_existing(self, skin):
        import zipfile
        if skin.path is None:
            return
        folder = skin.path
        if folder.is_file():
            cache = paths.config_dir() / "editing" / slugify(skin.name)
            shutil.rmtree(cache, ignore_errors=True)
            cache.mkdir(parents=True)
            with zipfile.ZipFile(folder) as zf:
                for member in zf.namelist():
                    target = (cache / member).resolve()
                    if str(target).startswith(str(cache.resolve())):
                        zf.extract(member, cache)
            found = next(iter(sorted(cache.rglob("skin.json"))), None)
            folder = found.parent if found else cache
            self.editing = None  # zipped skins are saved as a new folder skin
        else:
            self.editing = folder
        manifest = json.loads((folder / "skin.json").read_text("utf-8"))
        self.editing_manifest = manifest
        self.entries.clear()
        for i in range(self.roles.count()):
            self.roles.item(i).setIcon(QIcon())
        for role_name, spec in (manifest.get("cursors") or {}).items():
            try:
                role = Role(role_name)
            except ValueError:
                continue
            spec = {"file": spec} if isinstance(spec, str) else dict(spec)
            fname = spec.get("file") or (spec.get("files") or [None])[0]
            if not fname or not (folder / fname).exists():
                continue
            path = folder / fname
            hot = spec.get("hotspot")
            if hot is None:
                try:
                    hot = load_source(path.read_bytes(), path.suffix).hotspot
                except Exception:  # noqa: BLE001
                    hot = (0, 0)
            self.entries[role] = {
                "path": str(path), "hotspot": (int(hot[0]), int(hot[1])), "frames": int(spec.get("frames", 1)),
                "delay": int(spec.get("delay") or 0), "pixel_art": bool(spec.get("pixel_art")),
                "hotspot_set": "hotspot" in spec,
                "extra": {k: spec[k] for k in ("delays", "size") if k in spec},
            }
            try:
                src = self._source(self.entries[role])
                img = src.render(src.nominal).frames[0] if src.svg is not None else src.frames[0]
                self._set_icon(role, img)
            except Exception:  # noqa: BLE001
                pass
        self.name.setText(manifest.get("name") or skin.name)
        self.author.setText(manifest.get("author") or "")
        self.save_btn.setText(tr("Save changes") if self.editing else tr("Save to library"))
        self.save_new_btn.setVisible(self.editing is not None)
        self.roles.setCurrentRow(0)
        self._select(0)
        self.c.status.emit(tr("Editing '{name}'").format(name=self.name.text()))

    def save(self, as_new: bool = False):
        if not self.entries:
            QMessageBox.information(self, tr("Pack Builder"), tr("Add at least one image first."))
            return
        if Role.ARROW not in self.entries:
            QMessageBox.information(self, tr("Pack Builder"), tr("Please add an image for 'Normal Select'."))
            return
        name = self.name.text().strip() or "My Pack"
        in_place = self.editing is not None and self.editing.is_dir() and not as_new
        final = self.editing if in_place else unique_dir(paths.skins_dir() / slugify(name))
        # Build in a staging folder first: in-place edits may read from the folder being replaced.
        dest = unique_dir(paths.skins_dir() / f".staging-{slugify(name)}")
        dest.mkdir(parents=True)
        cursors = {}
        for role, e in self.entries.items():
            src = Path(e["path"])
            fname = f"{role.value}{src.suffix.lower()}"
            shutil.copyfile(src, dest / fname)
            spec = {"file": fname, **e.get("extra", {}), **self._spec(e)}
            if e.get("delay"):
                spec.pop("delays", None)
            if not e.get("hotspot_set") and src.suffix.lower() in (".cur", ".ani"):
                spec.pop("hotspot")
            cursors[role.value] = spec
        base = {k: v for k, v in self.editing_manifest.items() if k not in ("cursors", "generator")}
        manifest = {"format": 1, "category": "Custom", "tags": ["custom"], **base, "name": name,
                    "author": self.author.text().strip() or "Unknown", "cursors": cursors}
        (dest / "skin.json").write_text(json.dumps(manifest, indent=2), "utf-8")
        try:
            from ..skin import load_skin
            load_skin(dest)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(dest, ignore_errors=True)
            QMessageBox.warning(self, tr("Could not save"), str(exc))
            return
        if final.exists():
            shutil.rmtree(final)
        shutil.move(str(dest), final)
        skin = self.c.library.add_from_path(final)
        self.editing = final
        self.editing_manifest = manifest
        for role, e in self.entries.items():  # point entries at the saved copies
            e["path"] = str(final / cursors[role.value]["file"])
        self.save_btn.setText(tr("Save changes"))
        self.save_new_btn.setVisible(True)
        self.studio.saved.emit(skin.id)
        if skin.id == self.c.active_skin_id:
            self.c.apply_skin(skin.id, persist=False)
        self.c.status.emit(tr("Saved '{name}' to your library").format(name=skin.name))

