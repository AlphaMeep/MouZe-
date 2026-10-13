"""Dialog: find and import your downloaded Mouse X / Steam Workshop skins."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .. import paths
from ..formats import mousex
from ..i18n import tr
from ..skin import SUPPORTED_EXTS


def _thumb(item: mousex.WorkshopItem) -> QIcon:
    path = item.preview
    if path is None:
        for p in sorted(item.path.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS - {".svg", ".cur", ".ani", ".ico"}:
                path = p
                break
    if path is None:
        return QIcon()
    pm = QPixmap(str(path))
    if pm.isNull():
        return QIcon()
    return QIcon(pm.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class MouseXDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        self.imported: list[str] = []
        self.extra_dirs: list[Path] = []
        self.items: list[mousex.WorkshopItem] = []
        self.setWindowTitle(tr("Import from Mouse X / Steam Workshop"))
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        info = QLabel(tr(
            "MouZe looks for Mouse X skins you have subscribed to in every Steam library on this computer "
            "(steamapps/workshop/content/4255580). Skins are converted locally for your own use; they still "
            "belong to their creators. Mouse X's format is not public, so check hotspots after importing."))
        info.setWordWrap(True)
        info.setProperty("dim", True)
        lay.addWidget(info)
        self.list = QListWidget()
        self.list.setIconSize(QSize(48, 48))
        lay.addWidget(self.list, 1)
        self.status = QLabel()
        self.status.setProperty("dim", True)
        lay.addWidget(self.status)
        opts = QHBoxLayout()
        self.other_apps = QCheckBox(tr("Also scan other Steam cursor apps"))
        self.other_apps.toggled.connect(lambda _: self.scan())
        opts.addWidget(self.other_apps)
        opts.addStretch(1)
        lay.addLayout(opts)
        row = QHBoxLayout()
        for label, fn in ((tr("Scan again"), self.scan), (tr("Add folder…"), self.add_folder),
                          (tr("Look up names online"), self.lookup), (tr("Select all"), lambda: self._check_all(True)),
                          (tr("Select none"), lambda: self._check_all(False))):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton(tr("Close"))
        cancel.clicked.connect(self.accept)
        self.go = QPushButton(tr("Import selected"))
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.import_selected)
        bottom.addWidget(cancel)
        bottom.addWidget(self.go)
        lay.addLayout(bottom)
        self.scan()

    def scan(self):
        appids = tuple(mousex.KNOWN_APPS) if self.other_apps.isChecked() else (mousex.MOUSE_X_APPID,)
        self.items = mousex.find_workshop_items(appids, self.extra_dirs + mousex.mouse_x_local_skin_dirs())
        self._fill()
        libs = mousex.library_folders()
        if self.items:
            self.status.setText(tr("Found {n} item(s) in {libs} Steam library folder(s).").format(
                n=len(self.items), libs=len(libs)))
        elif libs:
            self.status.setText(tr("No downloaded Mouse X skins found. Subscribe to skins in Mouse X / Steam first, "
                                   "or use 'Add folder…'."))
        else:
            self.status.setText(tr("Steam was not found on this computer. Use 'Add folder…' to pick skin folders."))

    def _fill(self):
        self.list.clear()
        for item in self.items:
            it = QListWidgetItem(_thumb(item), f"{item.display_name}\n{item.app_name} · {item.item_id}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            it.setToolTip(str(item.path))
            self.list.addItem(it)

    def _check_all(self, on: bool):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("Folder containing skin folders"), str(Path.home()))
        if not d:
            return
        p = Path(d)
        # A single skin folder or a folder of skin folders both work.
        if any(f.is_file() and f.suffix.lower() in SUPPORTED_EXTS for f in p.iterdir()):
            self.items.append(mousex.WorkshopItem(mousex.MOUSE_X_APPID, p.name, p, *mousex._local_meta(p)))
            self._fill()
        else:
            self.extra_dirs.append(p)
            self.scan()

    def lookup(self):
        n = mousex.lookup_titles(self.items)
        self._fill()
        self.status.setText(tr("Got {n} name(s) from Steam.").format(n=n) if n
                            else tr("Could not reach Steam (or nothing to look up)."))

    def import_selected(self):
        chosen = [self.items[i] for i in range(self.list.count())
                  if self.list.item(i).checkState() == Qt.CheckState.Checked]
        errors = []
        for item in chosen:
            try:
                dest = mousex.import_item(item, paths.skins_dir())
                self.imported.append(self.c.library.add_from_path(dest).id)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{item.display_name}: {exc}")
        if errors:
            QMessageBox.warning(self, tr("Some imports failed"), "\n".join(errors))
        if self.imported:
            self.accept()
