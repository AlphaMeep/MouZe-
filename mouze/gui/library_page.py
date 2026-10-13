"""Library page: browse, search, preview, tweak and apply skins."""

from __future__ import annotations

import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import paths
from ..controller import SIZES
from ..formats import packs
from ..imaging import Adjustments
from ..qtrender import pil_to_qpixmap
from ..roles import Role
from . import theme
from .widgets import ColorButton, LabeledSlider, RoleGrid, TestArea

THUMB = QSize(120, 86)
MAX_DOWNLOAD = 50 * 1024 * 1024


def make_thumbnail(skin, frame: int = 0) -> QPixmap:
    pm = QPixmap(THUMB)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2a2a36"))
    p.drawRoundedRect(QRectF(0, 0, THUMB.width(), THUMB.height()), 10, 10)
    main = skin.render(Role.ARROW, 56)
    img = main.frames[frame % len(main.frames)]
    p.drawPixmap(14, 15, pil_to_qpixmap(img))
    for i, role in enumerate((Role.LINK, Role.TEXT, Role.BUSY)):
        a = skin.render(role, 24)
        p.drawPixmap(84, 6 + i * 26, pil_to_qpixmap(a.frames[0]))
    p.end()
    return pm


class LibraryPage(QWidget):
    remix_requested = Signal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        self.items: dict[str, QListWidgetItem] = {}
        self._thumb_queue: list[str] = []
        self._hover_id: str | None = None
        self._hover_frames: dict[str, list[QIcon]] = {}
        self._hover_idx = 0
        self.current_id: str | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        root.addWidget(split)

        # --- left: categories --------------------------------------------------
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 4, 12)
        t = QLabel("Library")
        t.setObjectName("title")
        ll.addWidget(t)
        self.count_label = QLabel()
        self.count_label.setProperty("dim", True)
        ll.addWidget(self.count_label)
        self.categories = QListWidget()
        self.categories.setObjectName("categories")
        self.categories.currentRowChanged.connect(lambda _: self.refilter())
        ll.addWidget(self.categories, 1)
        imp = QPushButton("Import…")
        imp.setMenu(self._import_menu())
        ll.addWidget(imp)
        left.setMinimumWidth(150)
        left.setMaximumWidth(210)
        split.addWidget(left)

        # --- centre: search + gallery ------------------------------------------
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(4, 12, 4, 4)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search skins, tags, authors…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        self.animated_only = QCheckBox("Animated")
        self.animated_only.toggled.connect(lambda _: self.refilter())
        self.sort = QComboBox()
        self.sort.addItems(["Library order", "Name A–Z", "Name Z–A"])
        self.sort.currentIndexChanged.connect(lambda _: self.refilter())
        bar.addWidget(self.search, 1)
        bar.addWidget(self.animated_only)
        bar.addWidget(self.sort)
        ml.addLayout(bar)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self.refilter)
        self.gallery = QListWidget()
        self.gallery.setObjectName("gallery")
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(THUMB)
        self.gallery.setGridSize(QSize(THUMB.width() + 22, THUMB.height() + 44))
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setWordWrap(True)
        self.gallery.setUniformItemSizes(True)
        self.gallery.setMouseTracking(True)
        self.gallery.setSpacing(2)
        self.gallery.currentItemChanged.connect(self._on_select)
        self.gallery.itemDoubleClicked.connect(lambda it: self.c.apply_skin(it.data(Qt.ItemDataRole.UserRole)))
        self.gallery.itemEntered.connect(self._on_hover)
        self.gallery.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.gallery.customContextMenuRequested.connect(self._context_menu)
        ml.addWidget(self.gallery, 1)
        split.addWidget(mid)

        # --- right: details -----------------------------------------------------
        self.detail = DetailPanel(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.detail)
        scroll.setMinimumWidth(470)
        split.addWidget(scroll)
        split.setStretchFactor(1, 1)
        split.setSizes([170, 560, 520])

        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(0)
        self._thumb_timer.timeout.connect(self._render_thumbs)
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(50)
        self._hover_timer.timeout.connect(self._animate_hover)

        self.c.skin_changed.connect(self._on_skin_changed)
        self.reload()

    # ----------------------------------------------------------------- populate
    def reload(self, select: str | None = None):
        self.items.clear()
        self.gallery.clear()
        self._hover_frames.clear()
        for skin in self.c.library:
            it = QListWidgetItem(self._item_text(skin))
            it.setData(Qt.ItemDataRole.UserRole, skin.id)
            it.setToolTip(f"{skin.name}\n{skin.meta.category} · {skin.meta.author}"
                          + ("\nAnimated" if skin.animated else ""))
            it.setSizeHint(self.gallery.gridSize())
            self.gallery.addItem(it)
            self.items[skin.id] = it
        self._thumb_queue = list(self.items)
        self._thumb_timer.start()
        current = self.categories.currentItem().text().split("  ")[0] if self.categories.currentItem() else "All"
        self.categories.blockSignals(True)
        self.categories.clear()
        groups = ["All", "Favorites", "Recent", "Animated", *self.c.library.categories()]
        for g in groups:
            self.categories.addItem(g)
        matches = self.categories.findItems(current, Qt.MatchFlag.MatchExactly)
        self.categories.setCurrentItem(matches[0] if matches else self.categories.item(0))
        self.categories.blockSignals(False)
        self.refilter()
        target = select or self.c.active_skin_id or self.c.settings["skin"]
        if target in self.items:
            self.gallery.setCurrentItem(self.items[target])
            self.gallery.scrollToItem(self.items[target])

    def _item_text(self, skin) -> str:
        star = "★ " if skin.id in self.c.settings["favorites"] else ""
        active = "● " if skin.id == self.c.active_skin_id else ""
        return f"{active}{star}{skin.name}"

    def _render_thumbs(self):
        # Render a few per event-loop pass so the UI stays responsive.
        for _ in range(6):
            if not self._thumb_queue:
                self._thumb_timer.stop()
                return
            sid = self._thumb_queue.pop(0)
            it = self.items.get(sid)
            skin = self.c.library.get(sid)
            if it is None or skin is None:
                continue
            try:
                it.setIcon(QIcon(make_thumbnail(skin)))
            except Exception as exc:  # noqa: BLE001
                it.setToolTip(f"Could not render: {exc}")

    def refilter(self):
        cat = self.categories.currentItem().text() if self.categories.currentItem() else "All"
        text = self.search.text()
        anim = True if self.animated_only.isChecked() else None
        if cat == "Favorites":
            skins = self.c.library.search(text, None, anim, ids=self.c.settings["favorites"])
        elif cat == "Recent":
            skins = self.c.library.search(text, None, anim, ids=self.c.settings["recent"])
        elif cat == "Animated":
            skins = self.c.library.search(text, None, True)
        elif cat == "All":
            skins = self.c.library.search(text, None, anim)
        else:
            skins = self.c.library.search(text, cat, anim)
        visible = {s.id for s in skins}
        for sid, it in self.items.items():
            it.setHidden(sid not in visible)
        order = self.sort.currentIndex()
        if order:
            self.gallery.sortItems(Qt.SortOrder.AscendingOrder if order == 1 else Qt.SortOrder.DescendingOrder)
        self.count_label.setText(f"{len(visible)} of {len(self.items)} skins")

    # -------------------------------------------------------------- selection
    def _on_select(self, it, _prev=None):
        if it is None:
            return
        self.current_id = it.data(Qt.ItemDataRole.UserRole)
        skin = self.c.library.get(self.current_id)
        if skin:
            self.detail.show_skin(skin)

    def _on_skin_changed(self, _sid):
        for sid, it in self.items.items():
            skin = self.c.library.get(sid)
            if skin:
                it.setText(self._item_text(skin))
        self.detail.refresh_state()

    def select(self, sid: str):
        if sid in self.items:
            self.gallery.setCurrentItem(self.items[sid])
            self.gallery.scrollToItem(self.items[sid])

    def _on_hover(self, it):
        sid = it.data(Qt.ItemDataRole.UserRole)
        if sid == self._hover_id:
            return
        if self._hover_id in self.items:
            frames = self._hover_frames.get(self._hover_id)
            if frames:
                self.items[self._hover_id].setIcon(frames[0])
        self._hover_id = sid
        skin = self.c.library.get(sid)
        if skin is not None and skin.animated:
            if sid not in self._hover_frames:
                n = len(skin.render(Role.ARROW, 56).frames)
                self._hover_frames[sid] = [QIcon(make_thumbnail(skin, i)) for i in range(n)]
            self._hover_idx = 0
            self._hover_timer.start()
        else:
            self._hover_timer.stop()

    def _animate_hover(self):
        frames = self._hover_frames.get(self._hover_id)
        it = self.items.get(self._hover_id)
        if not frames or it is None or not self.gallery.underMouse():
            self._hover_timer.stop()
            if frames and it is not None:
                it.setIcon(frames[0])
            self._hover_id = None
            return
        self._hover_idx = (self._hover_idx + 1) % len(frames)
        it.setIcon(frames[self._hover_idx])

    def _context_menu(self, pos):
        it = self.gallery.itemAt(pos)
        if it is None:
            return
        sid = it.data(Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        m.addAction("Apply", lambda: self.c.apply_skin(sid))
        fav = sid in self.c.settings["favorites"]
        m.addAction("Remove from favourites" if fav else "Add to favourites", lambda: self.toggle_favorite(sid))
        skin = self.c.library.get(sid)
        if skin is not None and getattr(skin, "recipe", None):
            m.addAction("Remix in Designer", lambda: self.remix_requested.emit(sid))
        if skin is not None and not skin.is_builtin:
            m.addAction("Delete", lambda: self.delete_skin(sid))
        m.exec(self.gallery.viewport().mapToGlobal(pos))

    def toggle_favorite(self, sid: str):
        self.c.settings.toggle_favorite(sid)
        self.c.settings.save()
        skin = self.c.library.get(sid)
        if skin and sid in self.items:
            self.items[sid].setText(self._item_text(skin))
        self.detail.refresh_state()
        if self.categories.currentItem() and self.categories.currentItem().text() == "Favorites":
            self.refilter()

    def delete_skin(self, sid: str):
        skin = self.c.library.get(sid)
        if skin is None:
            return
        if QMessageBox.question(self, "Delete skin", f"Delete '{skin.name}' from your library?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.c.library.delete(sid)
        if sid in self.c.settings["favorites"]:
            self.c.settings["favorites"].remove(sid)
        self.c.settings.save()
        self.reload()

    # ------------------------------------------------------------------ import
    def _import_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction("Files (cursor pack, theme, skin, images)…", self.import_files)
        m.addAction("Folder (Windows pack / Xcursor theme)…", self.import_folder)
        m.addAction("From URL…", self.import_url)
        m.addSeparator()
        m.addAction("Open skins folder", lambda: _open_folder(paths.skins_dir()))
        m.addAction("Reload library", self.reload_library)
        return m

    def reload_library(self):
        self.c.library.reload()
        self.reload()

    def import_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import cursors", str(Path.home()),
            "Cursors & packs (*.cur *.ani *.ico *.zip *.mouzeskin *.tar.gz *.tgz *.tar.xz *.png *.gif *.apng "
            "*.webp *.avif *.svg);;All files (*)")
        self.import_paths([Path(f) for f in files])

    def import_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Import a cursor pack folder", str(Path.home()))
        if d:
            self.import_paths([Path(d)])

    def import_url(self):
        url, ok = QInputDialog.getText(self, "Import from URL",
                                       "Direct link to a .zip, .mouzeskin, .cur, .ani or image:")
        if not ok or not url.strip():
            return
        url = url.strip()
        if urllib.parse.urlparse(url).scheme not in ("http", "https"):
            QMessageBox.warning(self, "Import", "Only http(s) links are supported.")
            return
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310 - scheme checked above
                data = resp.read(MAX_DOWNLOAD + 1)
            if len(data) > MAX_DOWNLOAD:
                raise ValueError("file is larger than 50 MB")
            name = Path(urllib.parse.urlparse(url).path).name or "download.zip"
            with tempfile.TemporaryDirectory() as tmp:
                f = Path(tmp) / name
                f.write_bytes(data)
                self.import_paths([f])
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import failed", str(exc))

    def import_paths(self, items: list[Path]):
        done, errors = [], []
        for p in items:
            try:
                dest = packs.import_path(p, paths.skins_dir())
                done.append(self.c.library.add_from_path(dest))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p.name}: {exc}")
        if done:
            self.reload(select=done[-1].id)
            self.c.status.emit(f"Imported {len(done)} skin(s)")
        if errors:
            QMessageBox.warning(self, "Some imports failed", "\n".join(errors))


def _open_folder(path: Path):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    path.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class DetailPanel(QWidget):
    def __init__(self, page: LibraryPage):
        super().__init__()
        self.page = page
        self.c = page.c
        self.skin = None
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 12, 12)

        head = QHBoxLayout()
        col = QVBoxLayout()
        self.title = QLabel("")
        self.title.setObjectName("title")
        self.subtitle = QLabel("")
        self.subtitle.setProperty("dim", True)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setProperty("dim", True)
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        col.addWidget(self.desc)
        head.addLayout(col, 1)
        lay.addLayout(head)

        btns = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self.apply)
        self.fav_btn = QPushButton("☆ Favourite")
        self.fav_btn.clicked.connect(lambda: self.skin and self.page.toggle_favorite(self.skin.id))
        self.export_btn = QPushButton("Export")
        self.export_btn.setMenu(self._export_menu())
        self.remix_btn = QPushButton("Remix")
        self.remix_btn.setToolTip("Open this skin in the Designer")
        self.remix_btn.clicked.connect(lambda: self.skin and self.page.remix_requested.emit(self.skin.id))
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(lambda: self.skin and self.page.delete_skin(self.skin.id))
        for b in (self.apply_btn, self.fav_btn, self.export_btn, self.remix_btn, self.delete_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        # previews
        pv = QGroupBox("All cursors")
        pvl = QVBoxLayout(pv)
        bgrow = QHBoxLayout()
        bgrow.addWidget(QLabel("Background"))
        self.bg = QComboBox()
        self.bg.addItems(["dark", "light", "checker"])
        self.bg.currentTextChanged.connect(lambda t: self.grid.set_background(t))
        bgrow.addWidget(self.bg)
        bgrow.addStretch(1)
        pvl.addLayout(bgrow)
        self.grid = RoleGrid(box=58, columns=6)
        pvl.addWidget(self.grid)
        lay.addWidget(pv)

        tg = QGroupBox("Try it - hover the boxes")
        tl = QVBoxLayout(tg)
        self.test = TestArea()
        tl.addWidget(self.test)
        lay.addWidget(tg)

        # adjustments
        ag = QGroupBox("Adjust (saved per skin)")
        form = QFormLayout(ag)
        self.size = QComboBox()
        for s in SIZES:
            self.size.addItem(f"{s} px", s)
        self.size.currentIndexChanged.connect(self._size_changed)
        form.addRow("Size (all skins)", self.size)
        self.hue = LabeledSlider(-180, 180, 0, 1, "{:+.0f}°")
        self.sat = LabeledSlider(0, 2, 1, 0.05, "{:.2f}")
        self.bri = LabeledSlider(0.3, 1.7, 1, 0.05, "{:.2f}")
        self.opa = LabeledSlider(0.2, 1, 1, 0.05, "{:.0%}")
        self.speed = LabeledSlider(0.25, 4, 1, 0.25, "{:.2f}×")
        for label, w in (("Hue", self.hue), ("Saturation", self.sat), ("Brightness", self.bri),
                         ("Opacity", self.opa), ("Animation speed", self.speed)):
            w.valueChanged.connect(self._adj_changed)
            form.addRow(label, w)
        checks = QGridLayout()
        self.mirror = QCheckBox("Left-handed (mirror)")
        self.invert = QCheckBox("Invert colours")
        self.gray = QCheckBox("Greyscale")
        self.shadow = QCheckBox("Drop shadow")
        self.outline = QCheckBox("Extra outline")
        self.outline_color = ColorButton("#000000")
        self.outline_color.colorChanged.connect(lambda _: self._adj_changed())
        self.tint_on = QCheckBox("Tint")
        self.tint = ColorButton("#00e5ff")
        self.tint.colorChanged.connect(lambda _: self._adj_changed())
        for i, w in enumerate((self.mirror, self.invert, self.gray, self.shadow)):
            checks.addWidget(w, i // 2, i % 2)
            w.toggled.connect(self._adj_changed)
        orow = QHBoxLayout()
        orow.addWidget(self.outline)
        orow.addWidget(self.outline_color)
        orow.addStretch(1)
        trow = QHBoxLayout()
        trow.addWidget(self.tint_on)
        trow.addWidget(self.tint)
        trow.addStretch(1)
        self.outline.toggled.connect(self._adj_changed)
        self.tint_on.toggled.connect(self._adj_changed)
        checks.addLayout(orow, 2, 0)
        checks.addLayout(trow, 2, 1)
        form.addRow(checks)
        reset = QPushButton("Reset adjustments")
        reset.clicked.connect(self._reset)
        form.addRow(reset)
        lay.addWidget(ag)
        lay.addStretch(1)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(600)
        self._apply_timer.timeout.connect(
            lambda: self.skin and self.c.apply_skin(self.skin.id, persist=False))

    def _export_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction("Windows cursor pack (.cur/.ani + install.inf)…", lambda: self.export("windows"))
        m.addAction("Linux Xcursor theme…", lambda: self.export("xcursor"))
        m.addAction("MouZe skin (.mouzeskin)…", lambda: self.export("skin"))
        m.addAction("Preview image (.png)…", lambda: self.export("preview"))
        return m

    # ---------------------------------------------------------------------- state
    def show_skin(self, skin):
        self.skin = skin
        self._loading = True
        self.title.setText(skin.name)
        tags = ", ".join(skin.meta.tags)
        self.subtitle.setText(f"{skin.meta.category} · by {skin.meta.author}" + (f" · {tags}" if tags else ""))
        self.desc.setText(skin.meta.description)
        self.desc.setVisible(bool(skin.meta.description))
        adj = self.c.adjustments(skin.id)
        idx = self.size.findData(int(self.c.settings["size"]))
        self.size.setCurrentIndex(idx if idx >= 0 else 2)
        self.hue.set_value(adj.hue)
        self.sat.set_value(adj.saturation)
        self.bri.set_value(adj.brightness)
        self.opa.set_value(adj.opacity)
        self.speed.set_value(adj.speed)
        self.mirror.setChecked(adj.mirror)
        self.invert.setChecked(adj.invert)
        self.gray.setChecked(adj.grayscale)
        self.shadow.setChecked(adj.shadow)
        self.outline.setChecked(adj.outline)
        self.outline_color.set_color(adj.outline_color)
        self.tint_on.setChecked(bool(adj.tint))
        if adj.tint:
            self.tint.set_color(adj.tint)
        self._loading = False
        self.remix_btn.setVisible(getattr(skin, "recipe", None) is not None)
        self.delete_btn.setVisible(not skin.is_builtin)
        self.refresh_state()
        self._refresh_preview()

    def refresh_state(self):
        if self.skin is None:
            return
        fav = self.skin.id in self.c.settings["favorites"]
        self.fav_btn.setText("★ Favourite" if fav else "☆ Favourite")
        active = self.skin.id == self.c.active_skin_id
        self.apply_btn.setText("Re-apply" if active else "Apply")

    def current_adj(self) -> Adjustments:
        return Adjustments(
            hue=int(self.hue.value()), saturation=round(self.sat.value(), 2),
            brightness=round(self.bri.value(), 2), opacity=round(self.opa.value(), 2),
            speed=round(self.speed.value(), 2), mirror=self.mirror.isChecked(), invert=self.invert.isChecked(),
            grayscale=self.gray.isChecked(), shadow=self.shadow.isChecked(), outline=self.outline.isChecked(),
            outline_color=self.outline_color.color(),
            tint=self.tint.color() if self.tint_on.isChecked() else "")

    def preview_size(self) -> int:
        return max(32, min(64, int(self.size.currentData() or 32)))

    def _refresh_preview(self):
        if self.skin is None:
            return
        adj = self.current_adj()
        self.grid.set_skin(self.skin, self.preview_size(), adj)
        self.test.set_skin(self.skin, int(self.size.currentData() or 32), adj)

    def _adj_changed(self, *_):
        if self._loading or self.skin is None:
            return
        self.c.set_adjustments(self.skin.id, self.current_adj(), apply=False)
        self._preview_timer.start()
        if self.skin.id == self.c.active_skin_id:
            self._apply_timer.start()

    def _size_changed(self, *_):
        if self._loading:
            return
        size = int(self.size.currentData())
        if size != int(self.c.settings["size"]):
            self.c.set_size(size)
        self._preview_timer.start()

    def _reset(self):
        if self.skin is None:
            return
        self.c.set_adjustments(self.skin.id, Adjustments(), apply=True)
        self.show_skin(self.skin)

    def apply(self):
        if self.skin is not None:
            self.c.apply_skin(self.skin.id)

    def export(self, kind: str):
        if self.skin is None:
            return
        skin, adj = self.skin, self.current_adj()
        size = max(32, int(self.size.currentData() or 32))
        base = str(Path.home() / skin.name.replace("/", "-"))
        try:
            if kind == "windows":
                d = QFileDialog.getExistingDirectory(self, "Choose a folder for the cursor pack", str(Path.home()))
                if not d:
                    return
                dest = packs.export_windows_pack(skin, Path(d) / skin.name.replace("/", "-"), size, adj)
            elif kind == "xcursor":
                d = QFileDialog.getExistingDirectory(self, "Choose a folder for the Xcursor theme", str(Path.home()))
                if not d:
                    return
                dest = packs.export_xcursor_theme(skin, d, adj=adj)
            elif kind == "skin":
                f, _ = QFileDialog.getSaveFileName(self, "Save skin", base + ".mouzeskin", "MouZe skin (*.mouzeskin)")
                if not f:
                    return
                dest = packs.export_skin(skin, f, max(64, size), adj)
            else:
                f, _ = QFileDialog.getSaveFileName(self, "Save preview", base + ".png", "PNG image (*.png)")
                if not f:
                    return
                dest = packs.export_preview_png(skin, f, 64, adj)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self.c.status.emit(f"Exported to {dest}")


__all__ = ["LibraryPage", "theme"]
