"""Discover page: seasonal picks, staff picks, random finds and community catalogs."""

from __future__ import annotations

import datetime as dt
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import community, paths
from ..builtin.catalog import SEASON_BY_MONTH, STAFF_PICKS
from ..i18n import tr
from . import theme
from .library_page import THUMB, make_thumbnail

COLUMNS = 5
SEASON_NAMES = {"halloween": "Halloween", "autumn": "Autumn", "winter": "Winter", "christmas": "Holidays",
                "newyear": "New Year", "valentine": "Valentine's Day", "spring": "Spring", "summer": "Summer"}


class SkinCard(QFrame):
    def __init__(self, page: DiscoverPage, skin):
        super().__init__()
        self.setObjectName("panel")
        self.setFixedWidth(THUMB.width() + 56)
        self.setStyleSheet("QPushButton { padding: 6px 8px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        pic = QLabel()
        pic.setPixmap(make_thumbnail(skin))
        pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name = QLabel(skin.name)
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel(tr(skin.meta.category))
        sub.setProperty("dim", True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout()
        apply_btn = QPushButton(tr("Apply"))
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(lambda: page.c.apply_skin(skin.id))
        more = QPushButton(tr("Details"))
        more.clicked.connect(lambda: page.open_skin.emit(skin.id))
        row.addWidget(apply_btn)
        row.addWidget(more)
        for w in (pic, name, sub):
            lay.addWidget(w)
        lay.addLayout(row)


class CommunityCard(QFrame):
    def __init__(self, page: DiscoverPage, entry: community.CatalogEntry):
        super().__init__()
        self.page = page
        self.entry = entry
        self.setObjectName("panel")
        self.setFixedWidth(THUMB.width() + 56)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.pic = QLabel(tr("Loading preview…"))
        self.pic.setFixedSize(THUMB)
        self.pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pic.setStyleSheet(f"background: {theme.BG_3}; border-radius: 10px; color: {theme.TEXT_DIM};")
        name = QLabel(entry.name)
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        by = QLabel(tr("by {author}").format(author=entry.author) + (" · " + tr("animated") if entry.animated else ""))
        by.setProperty("dim", True)
        by.setAlignment(Qt.AlignmentFlag.AlignCenter)
        by.setWordWrap(True)
        self.setToolTip(entry.description or entry.name)
        self.button = QPushButton()
        self.button.clicked.connect(self.toggle)
        lay.addWidget(self.pic, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(name)
        lay.addWidget(by)
        lay.addWidget(self.button)
        self.refresh()

    def refresh(self):
        sub = self.page.c.settings["subscriptions"].get(self.entry.key)
        if sub is None:
            self.button.setText(tr("Subscribe"))
            self.button.setObjectName("primary")
        elif sub.get("version") != self.entry.version:
            self.button.setText(tr("Update"))
            self.button.setObjectName("primary")
        else:
            self.button.setText(tr("Unsubscribe"))
            self.button.setObjectName("")
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)

    def set_preview(self, data: bytes):
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.pic.setPixmap(pm.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        else:
            self.pic.setText(tr("No preview"))

    def toggle(self):
        c = self.page.c
        sub = c.settings["subscriptions"].get(self.entry.key)
        self.button.setEnabled(False)
        try:
            if sub is not None and sub.get("version") == self.entry.version:
                community.unsubscribe(self.entry.key, c.settings, paths.skins_dir())
                c.status.emit(tr("Unsubscribed from {name}").format(name=self.entry.name))
            else:
                folder = community.subscribe(self.entry, c.settings, paths.skins_dir())
                c.library.add_from_path(folder)
                c.status.emit(tr("Subscribed to {name} - it is now in your library").format(name=self.entry.name))
            c.library.reload()
            c.library_changed.emit()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("Community"), str(exc))
        finally:
            self.button.setEnabled(True)
            self.refresh()


class _Fetcher(QObject):
    catalog_ready = Signal(str, str, list, str)   # url, name, entries, error
    preview_ready = Signal(str, bytes)


class DiscoverPage(QWidget):
    open_skin = Signal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        self.fetcher = _Fetcher()
        self.fetcher.catalog_ready.connect(self._show_catalog)
        self.fetcher.preview_ready.connect(self._show_preview)
        self.community_cards: dict[str, CommunityCard] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(16, 12, 16, 16)
        t = QLabel(tr("Discover"))
        t.setObjectName("title")
        self.lay.addWidget(t)
        sub = QLabel(tr("Seasonal skins, staff picks, random finds and community skins you can subscribe to."))
        sub.setProperty("dim", True)
        self.lay.addWidget(sub)

        self.season_box = self._section("")
        self.picks_box = self._section(tr("Staff picks"))
        rnd_head = QHBoxLayout()
        self.random_box = self._section(tr("Random picks"), rnd_head)
        shuffle = QPushButton(tr("Shuffle"))
        shuffle.clicked.connect(self.fill_random)
        rnd_head.addWidget(shuffle)
        self.recent_box = self._section(tr("Recently added to your library"))

        cat_head = QHBoxLayout()
        self.catalog = QComboBox()
        self.catalog.setMinimumWidth(320)
        refresh = QPushButton(tr("Refresh"))
        refresh.clicked.connect(self.load_catalog)
        add = QPushButton(tr("Add catalog…"))
        add.clicked.connect(self.add_catalog)
        cat_head.addWidget(self.catalog, 1)
        cat_head.addWidget(refresh)
        cat_head.addWidget(add)
        self.community_box = self._section(tr("Community skins"), cat_head)
        self.community_status = QLabel()
        self.community_status.setProperty("dim", True)
        self.community_status.setWordWrap(True)
        self.lay.addWidget(self.community_status)
        self.lay.addStretch(1)
        self.catalog.currentIndexChanged.connect(lambda _: self.load_catalog())
        self.c.library_changed.connect(self.fill_local)
        self._loaded_once = False
        self.fill_local()

    def _section(self, title: str, header_extra: QHBoxLayout | None = None) -> QGridLayout:
        head = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setObjectName("h2")
        head.addWidget(lbl)
        head.addStretch(1)
        if header_extra is not None:
            head.addLayout(header_extra)
        self.lay.addSpacing(10)
        self.lay.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid.title_label = lbl
        self.lay.addLayout(grid)
        return grid

    @staticmethod
    def _clear(grid: QGridLayout):
        while grid.count():
            w = grid.takeAt(0).widget()
            if w is not None:
                w.deleteLater()

    def _fill(self, grid: QGridLayout, skins, limit: int = COLUMNS * 2):
        self._clear(grid)
        for i, skin in enumerate(skins[:limit]):
            grid.addWidget(SkinCard(self, skin), i // COLUMNS, i % COLUMNS)
        if not skins:
            empty = QLabel(tr("Nothing here yet."))
            empty.setProperty("dim", True)
            grid.addWidget(empty, 0, 0)

    def current_seasons(self, today: dt.date | None = None) -> list[str]:
        return SEASON_BY_MONTH[(today or dt.date.today()).month]

    def fill_local(self):
        lib = self.c.library
        seasons = self.current_seasons()
        self.season_box.title_label.setText(tr("This season: {names}").format(
            names=", ".join(tr(SEASON_NAMES.get(s, s)) for s in seasons)))
        seasonal = [s for s in lib if any(t in s.meta.tags for t in seasons)]
        seasonal += [s for s in lib if s.meta.category == "Seasonal" and s not in seasonal]
        self._fill(self.season_box, seasonal, COLUMNS)
        self._fill(self.picks_box, [lib.get(i) for i in STAFF_PICKS if lib.get(i)])
        self.fill_random()
        user = [s for s in lib if not s.is_builtin and s.path is not None and s.path.exists()]
        user.sort(key=lambda s: s.path.stat().st_mtime, reverse=True)
        self._fill(self.recent_box, user, COLUMNS)
        self.catalog.blockSignals(True)
        current = self.catalog.currentText()
        self.catalog.clear()
        for url in self.c.settings["catalogs"]:
            self.catalog.addItem(url)
        if current:
            self.catalog.setCurrentText(current)
        self.catalog.blockSignals(False)

    def fill_random(self):
        import random
        skins = list(self.c.library)
        random.shuffle(skins)
        self._fill(self.random_box, skins, COLUMNS)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if not self._loaded_once:
            self._loaded_once = True
            self.load_catalog()

    # ------------------------------------------------------------------ community
    def add_catalog(self):
        url, ok = QInputDialog.getText(self, tr("Add catalog"), tr("Catalog URL (index.json) or local path:"))
        if ok and url.strip():
            cats = self.c.settings["catalogs"]
            if url.strip() not in cats:
                cats.append(url.strip())
                self.c.settings.save()
            self.fill_local()
            self.catalog.setCurrentText(url.strip())
            self.load_catalog()

    def load_catalog(self):
        url = self.catalog.currentText()
        if not url:
            return
        self.community_status.setText(tr("Loading {url}…").format(url=url))
        self._clear(self.community_box)
        self.community_cards.clear()

        def work():
            try:
                name, entries = community.fetch_catalog(url)
                self.fetcher.catalog_ready.emit(url, name, entries, "")
            except Exception as exc:  # noqa: BLE001
                self.fetcher.catalog_ready.emit(url, "", [], str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _show_catalog(self, url: str, name: str, entries: list, error: str):
        if url != self.catalog.currentText():
            return
        if error:
            self.community_status.setText(tr("Could not load the catalog ({error}). You can still import skins "
                                             "from files.").format(error=error))
            return
        self.community_status.setText(tr("{name}: {n} skin(s). Subscribed skins appear in your library and "
                                         "update automatically.").format(name=name, n=len(entries)))
        for i, entry in enumerate(entries):
            card = CommunityCard(self, entry)
            self.community_cards[entry.preview or entry.key] = card
            self.community_box.addWidget(card, i // COLUMNS, i % COLUMNS)
            if entry.preview:
                threading.Thread(target=self._fetch_preview, args=(entry.preview,), daemon=True).start()
            else:
                card.set_preview(b"")

    def _fetch_preview(self, url: str):
        try:
            data = community.read_bytes(url, limit=2_000_000)
        except Exception:  # noqa: BLE001
            data = b""
        self.fetcher.preview_ready.emit(url, data)

    def _show_preview(self, url: str, data: bytes):
        card = self.community_cards.get(url)
        if card is not None:
            try:
                card.set_preview(data)
            except RuntimeError:  # card deleted after a refresh
                pass
