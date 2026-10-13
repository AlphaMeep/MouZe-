"""Dark UI theme."""

ACCENT = "#7c5cff"
ACCENT_2 = "#00d1ff"
BG = "#121218"
BG_2 = "#1a1a23"
BG_3 = "#23232f"
BORDER = "#2e2e3d"
TEXT = "#e8e8f0"
TEXT_DIM = "#9a9ab0"

QSS = f"""
* {{ font-size: 13px; }}
QWidget {{ background: {BG}; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {BG_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QLabel#title {{ font-size: 20px; font-weight: 600; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#dim, QLabel[dim="true"] {{ color: {TEXT_DIM}; }}
QListWidget#nav {{ background: {BG_2}; border: none; padding: 8px 6px; outline: 0; }}
QListWidget#nav::item {{ padding: 10px 12px; border-radius: 8px; margin: 2px 0; }}
QListWidget#nav::item:selected {{ background: {ACCENT}; color: white; }}
QListWidget#nav::item:hover:!selected {{ background: {BG_3}; }}
QListWidget#categories {{ background: transparent; border: none; outline: 0; }}
QListWidget#categories::item {{ padding: 6px 10px; border-radius: 6px; }}
QListWidget#categories::item:selected {{ background: {BG_3}; color: {ACCENT_2}; }}
QListWidget#gallery {{ background: {BG}; border: none; outline: 0; }}
QListWidget#gallery::item {{ border-radius: 10px; padding: 6px; margin: 4px; color: {TEXT}; }}
QListWidget#gallery::item:selected {{ background: {BG_3}; border: 1px solid {ACCENT}; }}
QListWidget#gallery::item:hover:!selected {{ background: {BG_2}; }}
QFrame#panel, QGroupBox {{ background: {BG_2}; border: 1px solid {BORDER}; border-radius: 10px; }}
QGroupBox {{ margin-top: 18px; padding: 12px 10px 10px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {TEXT_DIM}; }}
QGroupBox QWidget, QFrame#panel QLabel {{ background: transparent; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit, QKeySequenceEdit, QPlainTextEdit {{
    background: {BG_3}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {BG_3}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; }}
QPushButton {{ background: {BG_3}; border: 1px solid {BORDER}; border-radius: 7px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: #8f74ff; }}
QPushButton#danger {{ color: #ff6b81; }}
QPushButton:checked {{ background: {ACCENT}; color: white; border: none; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {BORDER}; background: {BG_3}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 30px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{ background: {BG_2}; padding: 8px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {BG_3}; color: {ACCENT_2}; }}
QTableWidget {{ background: {BG_2}; border: 1px solid {BORDER}; border-radius: 8px; gridline-color: {BORDER}; }}
QHeaderView::section {{ background: {BG_3}; border: none; padding: 6px; color: {TEXT_DIM}; }}
QStatusBar {{ background: {BG_2}; color: {TEXT_DIM}; }}
QMenu {{ background: {BG_2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QSplitter::handle {{ background: {BG}; }}
"""
