"""Main window, system tray and app icon."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ..builtin.procedural import ProceduralSkin
from ..qtrender import pil_to_qpixmap
from ..roles import Role
from ..skin import SkinMeta
from .effects_page import EffectsPage
from .library_page import LibraryPage
from .profiles_page import ProfilesPage
from .settings_page import SettingsPage
from .studio_page import StudioPage

NAV = [("Library", "Browse and apply skins"), ("Effects", "Trails, clicks, halo, spotlight"),
       ("Profiles", "Per-app and time-based skins"), ("Studio", "Design or build your own"),
       ("Settings", "Startup, hotkeys, restore")]


def app_icon() -> QIcon:
    skin = ProceduralSkin("icon", SkinMeta("icon"), {"pointer": "dart", "style": "gradient",
                                                    "gradient": ["#7c5cff", "#00d1ff"], "outline": "#0b0b14",
                                                    "outline_width": 1.8})
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(pil_to_qpixmap(skin.render(Role.ARROW, s).frames[0]))
    return icon


def nav_icon(name: str) -> QIcon:
    recipes = {
        "Library": ("classic", Role.ARROW), "Effects": ("modern", Role.BUSY), "Profiles": ("modern", Role.PERSON),
        "Studio": ("classic", Role.HANDWRITING), "Settings": ("classic", Role.MOVE),
    }
    pointer, role = recipes[name]
    skin = ProceduralSkin("nav", SkinMeta("nav"), {"pointer": pointer, "style": "solid", "fill": "#e8e8f0",
                                                  "outline": "#121218", "accent": "#00d1ff"})
    return QIcon(pil_to_qpixmap(skin.render(role, 24).frames[0]))


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setWindowTitle("MouZe")
        self.setWindowIcon(app_icon())
        self.resize(1360, 860)
        self.setAcceptDrops(True)
        self._really_quit = False

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QWidget()
        side.setStyleSheet("background: #1a1a23;")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 16, 10, 12)
        brand = QLabel()
        brand.setPixmap(app_icon().pixmap(QSize(36, 36)))
        name = QLabel("MouZe")
        name.setStyleSheet("font-size: 22px; font-weight: 700; background: transparent;")
        br = QHBoxLayout()
        br.addWidget(brand)
        br.addWidget(name)
        br.addStretch(1)
        sl.addLayout(br)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setIconSize(QSize(22, 22))
        for title, tip in NAV:
            it = QListWidgetItem(nav_icon(title), title)
            it.setToolTip(tip)
            self.nav.addItem(it)
        self.nav.setFixedWidth(180)
        sl.addWidget(self.nav, 1)
        self.active_label = QLabel()
        self.active_label.setWordWrap(True)
        self.active_label.setStyleSheet("color: #9a9ab0; background: transparent; font-size: 11px;")
        sl.addWidget(self.active_label)
        root.addWidget(side)

        self.stack = QStackedWidget()
        self.library = LibraryPage(controller)
        self.effects = EffectsPage(controller)
        self.profiles = ProfilesPage(controller)
        self.studio = StudioPage(controller)
        self.settings_page = SettingsPage(controller)
        for w in (self.library, self.effects, self.profiles, self.studio, self.settings_page):
            self.stack.addWidget(w)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.library.remix_requested.connect(self._remix)
        self.studio.saved.connect(self._saved)
        self.c.status.connect(lambda m: self.statusBar().showMessage(m, 8000))
        self.c.skin_changed.connect(self._update_active)
        self.c.busy_changed.connect(lambda b: b and self.statusBar().showMessage("Applying…"))
        self.c.show_window_requested.connect(self.bring_to_front)
        self._update_active()

        self.tray = Tray(self)

    def _update_active(self, *_):
        skin = self.c.skin
        self.active_label.setText(f"Active: {skin.name}\n{self.c.size()} px" if skin else "")
        self.tray.refresh() if hasattr(self, "tray") else None

    def _remix(self, sid):
        self.nav.setCurrentRow(3)
        self.studio.remix(sid)

    def _saved(self, sid):
        self.library.reload(select=sid)

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # drag & drop import --------------------------------------------------------
    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        files = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.nav.setCurrentRow(0)
            self.library.import_paths(files)

    def closeEvent(self, e):  # noqa: N802
        if (not self._really_quit and self.c.settings["minimize_to_tray"]
                and QSystemTrayIcon.isSystemTrayAvailable()):
            e.ignore()
            self.hide()
            self.tray.notify_once()
            return
        self.quit()

    def quit(self):
        self._really_quit = True
        self.c.shutdown()
        self.tray.hide()
        QApplication.instance().quit()


class Tray(QSystemTrayIcon):
    def __init__(self, window: MainWindow):
        super().__init__(app_icon(), window)
        self.w = window
        self.c = window.c
        self._notified = False
        self.setToolTip("MouZe")
        self.menu = QMenu()
        self.setContextMenu(self.menu)
        self.menu.aboutToShow.connect(self.refresh)
        self.activated.connect(self._activated)
        self.refresh()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.show()

    def refresh(self):
        m = self.menu
        m.clear()
        m.addAction("Open MouZe", self.w.bring_to_front)
        m.addSeparator()
        favs = [self.c.library.get(i) for i in self.c.settings["favorites"]]
        favs = [s for s in favs if s is not None]
        sub = m.addMenu("Favourites")
        if not favs:
            a = sub.addAction("Star skins in the Library to see them here")
            a.setEnabled(False)
        for s in favs[:30]:
            act = QAction(("● " if s.id == self.c.active_skin_id else "") + s.name, sub)
            act.triggered.connect(lambda _=False, sid=s.id: self.c.apply_skin(sid))
            sub.addAction(act)
        recent = [self.c.library.get(i) for i in self.c.settings["recent"][:8]]
        rsub = m.addMenu("Recent")
        for s in [r for r in recent if r is not None]:
            act = QAction(s.name, rsub)
            act.triggered.connect(lambda _=False, sid=s.id: self.c.apply_skin(sid))
            rsub.addAction(act)
        m.addAction("Shuffle", self.c.shuffle_now)
        m.addSeparator()
        eff = QAction("Effects", m)
        eff.setCheckable(True)
        eff.setChecked(bool(self.c.effects_cfg().get("enabled")))
        eff.toggled.connect(self.c.set_effects_enabled)
        m.addAction(eff)
        m.addAction("Locate cursor", self.c.locate)
        m.addAction("Spotlight on/off", self.c.toggle_spotlight)
        m.addSeparator()
        m.addAction("Restore my previous cursors", lambda: self.c.restore_default(True))
        m.addSeparator()
        m.addAction("Quit MouZe", self.w.quit)
        skin = self.c.skin
        self.setToolTip(f"MouZe - {skin.name}" if skin else "MouZe")

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.w.isVisible() and not self.w.isMinimized():
                self.w.hide()
            else:
                self.w.bring_to_front()

    def notify_once(self):
        if not self._notified:
            self._notified = True
            self.showMessage("MouZe is still running", "Effects, hotkeys and profiles keep working. "
                             "Use the tray icon to reopen or quit.", app_icon(), 4000)

