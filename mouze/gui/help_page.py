"""Help & FAQ page."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from .. import __version__, paths
from ..i18n import tr
from . import theme

FAQ = [
    ("How do I change my cursor?",
     "Open <b>Library</b>, pick a skin, try it in the <i>Try it</i> boxes, then click <b>Apply</b>. The cursor "
     "changes everywhere, and it stays changed even after you close MouZe."),
    ("How do I get my old cursor back?",
     "Settings &rarr; <b>Restore my previous cursors</b>, the tray menu, or the panic hotkey "
     "<b>Ctrl+Alt+R</b>. MouZe backs up your original cursor scheme before changing anything."),
    ("Can I use my Mouse X skins?",
     "Yes. Library &rarr; Import &rarr; <b>From Mouse X / Steam Workshop</b> finds the skins you subscribed to "
     "in every Steam library and converts them. Mouse X does not publish its file format, so the import is "
     "best-effort: if a click point looks off, open the skin in Studio &rarr; Pack Builder and click the right "
     "spot. Imported skins still belong to their creators - please don't redistribute them."),
    ("What other cursor formats can I import?",
     "Windows .cur/.ani packs (with or without install.inf), Linux Xcursor themes, Linux theme sources "
     "(xcursorgen), Hyprland hyprcursor themes, macOS Mousecape .cape files, CSS cursor packs from websites and "
     "browser extensions, .mouzeskin files, and loose PNG/GIF/APNG/WebP/AVIF/SVG images or numbered frame "
     "sequences. Drag files onto the window or use Library &rarr; Import."),
    ("How do I make my own cursor?",
     "Studio &rarr; <b>Designer</b> builds a full set from a shape, a style and colours. Studio &rarr; <b>Pack "
     "Builder</b> turns your own images into a skin; click the image to set the hotspot (the exact pixel that "
     "clicks). Use <b>Open existing skin</b> to edit a skin you already have."),
    ("How do I share a skin?",
     "Library &rarr; Export &rarr; <b>MouZe skin (.mouzeskin)</b>, or a Windows pack, Linux theme, macOS cape "
     "or CSS pack. To publish to everyone, add it to a community catalog (see the README) and people can "
     "subscribe to it from Discover."),
    ("Does MouZe work with games and anti-cheat?",
     "MouZe never hooks or injects into other programs. Cursors are applied the same way Windows' own Mouse "
     "settings do it. Effects are a separate click-through window that pauses automatically when a game is "
     "fullscreen. Games that draw their own cursor will still show theirs."),
    ("Why is my cursor blurry or the wrong size?",
     "Pick a size in Library &rarr; Adjust. You can also give one skin its own size. When you change monitors or "
     "display scaling MouZe re-renders the cursors automatically. If it doesn't, press <b>Restart MouZe</b> in "
     "Settings."),
    ("The cursor did not change in some apps.",
     "Some apps only notice a new cursor theme after they restart (common on Linux). On Windows, apps that use "
     "their own custom cursors keep using them."),
    ("What is silent running?",
     "With silent running on, MouZe starts hidden in the system tray and shows no pop-up notifications. Open "
     "it again from the tray icon or with Ctrl+Alt+M."),
]


SHORTCUTS = [
    ("Next / previous favourite skin", "Ctrl+Alt+→ / ←"), ("Cursor size up / down", "Ctrl+Alt+↑ / ↓"),
    ("Toggle effects", "Ctrl+Alt+E"), ("Locate cursor", "Ctrl+Alt+L"), ("Toggle spotlight", "Ctrl+Alt+S"),
    ("Restore original cursors", "Ctrl+Alt+R"), ("Show MouZe", "Ctrl+Alt+M"),
]


class HelpPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 16)
        t = QLabel(tr("Help & FAQ"))
        t.setObjectName("title")
        lay.addWidget(t)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setStyleSheet(f"QTextBrowser {{ background: {theme.BG_2}; border: 1px solid {theme.BORDER}; "
                           "border-radius: 10px; padding: 12px; }")
        parts = [f"<p style='color:{theme.TEXT_DIM}'>MouZe {__version__}. " + tr("Report bugs or ask questions at") + " "
                 "<a style='color:#00d1ff' href='https://github.com/AlphaMeep/MouZe-/issues'>"
                 "github.com/AlphaMeep/MouZe-/issues</a>.</p>"]
        for q, a in FAQ:
            parts.append(f"<h3 style='margin-bottom:4px'>{tr(q)}</h3><p style='margin-top:0'>{tr(a)}</p>")
        parts.append("<h3>" + tr("Keyboard shortcuts") + "</h3><ul>" + "".join(
            f"<li><b>{combo}</b> - {tr(label)}</li>" for label, combo in SHORTCUTS) + "</ul>")
        view.setHtml("".join(parts))
        lay.addWidget(view, 1)
        row = QHBoxLayout()
        for label, fn in ((tr("Restart MouZe"), self.c.restart),
                          (tr("Restore my previous cursors"), lambda: self.c.restore_default(True)),
                          (tr("Open settings folder"), self._open_cfg)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

    def _open_cfg(self):
        from .library_page import _open_folder
        _open_folder(paths.config_dir())
