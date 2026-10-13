"""GUI entry point."""

from __future__ import annotations

import logging
import sys


def run_gui(minimized: bool = False) -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MouZe")
    app.setOrganizationName("MouZe")
    app.setQuitOnLastWindowClosed(False)

    from .controller import Controller
    from .gui.main_window import MainWindow
    from .gui.theme import QSS

    app.setStyleSheet(QSS)
    from .i18n import set_language

    controller = Controller()
    set_language(controller.settings["language"])
    window = MainWindow(controller)
    controller.start()
    s = controller.settings
    if not (minimized or s["start_minimized"] or s["silent_running"]):
        window.show()
    app.aboutToQuit.connect(lambda: window._really_quit or controller.shutdown())
    return app.exec()


def main() -> int:
    return run_gui(minimized="--minimized" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
