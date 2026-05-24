def get_stylesheet() -> str:
    return """
/* ═══════════════════════════════════════════════════════
   CHANDRAMA SOLUTIONS — LIGHT THEME
   chandramasolutions.com
═══════════════════════════════════════════════════════ */

/* ── Palette ──────────────────────────────────────────
   bg-primary:    #F8F9FA
   bg-secondary:  #FFFFFF
   bg-tertiary:   #F0F2F5
   accent:        #E55A28
   accent-light:  #FF6B35
   accent-dark:   #C44015
   text-primary:  #1A1A24
   text-secondary:#5A5A6A
   text-muted:    #8A8A9A
   border:        #E0E0E0
   border-hover:  #CCCCCC
─────────────────────────────────────────────────────── */

QMainWindow, QWidget {
    background-color: #F8F9FA;
    color: #1A1A24;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QDialog {
    background-color: #FFFFFF;
    color: #1A1A24;
}

/* ── Menu bar ─────────────────────────────────────── */
QMenuBar {
    background-color: #FFFFFF;
    color: #1A1A24;
    border-bottom: 1px solid #E0E0E0;
    padding: 2px 4px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    background-color: #F0F2F5;
    color: #E55A28;
}

QMenu {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    padding: 4px 0;
}
QMenu::item {
    padding: 6px 20px 6px 12px;
    color: #1A1A24;
}
QMenu::item:selected {
    background-color: #F0F2F5;
    color: #E55A28;
}
QMenu::separator {
    height: 1px;
    background: #E0E0E0;
    margin: 4px 8px;
}

/* ── Toolbar ──────────────────────────────────────── */
QToolBar {
    background-color: #F0F2F5;
    border: none;
    spacing: 2px;
    padding: 4px;
}
QToolBar::separator {
    width: 1px;
    background: #E0E0E0;
    margin: 4px 2px;
}

/* ── Push Buttons ─────────────────────────────────── */
QPushButton {
    background-color: #E55A28;
    color: #FFFFFF;
    border: none;
    border-radius: 5px;
    padding: 7px 18px;
    font-weight: 600;
    font-size: 13px;
    min-height: 28px;
}
QPushButton:hover { background-color: #FF6B35; }
QPushButton:pressed { background-color: #C44015; }
QPushButton:disabled { background-color: #CCCCCC; color: #FFFFFF; }

QPushButton[secondary="true"] {
    background-color: transparent;
    color: #E55A28;
    border: 1.5px solid #E55A28;
}
QPushButton[secondary="true"]:hover {
    background-color: #FFF3EF;
    border-color: #FF6B35;
    color: #FF6B35;
}
QPushButton[secondary="true"]:pressed {
    background-color: #FFE6DC;
    border-color: #C44015;
    color: #C44015;
}

QPushButton[outlined="true"] {
    background-color: transparent;
    color: #5A5A6A;
    border: 1.5px solid #E0E0E0;
}
QPushButton[outlined="true"]:hover {
    background-color: #F0F2F5;
    border-color: #CCCCCC;
}
QPushButton[outlined="true"]:pressed {
    background-color: #E8E8E8;
}

/* ── Tool Buttons ─────────────────────────────────── */
QToolButton {
    background-color: transparent;
    border: none;
    border-radius: 5px;
    padding: 5px;
    color: #1A1A24;
    font-size: 13px;
}
QToolButton:hover {
    background-color: #E8E8E8;
    color: #E55A28;
}
QToolButton:checked, QToolButton:pressed {
    background-color: #E55A28;
    color: #FFFFFF;
}
QToolButton::menu-indicator { image: none; width: 0; }

/* ── CheckBox ─────────────────────────────────────── */
QCheckBox {
    spacing: 6px;
    color: #1A1A24;
}
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1.5px solid #E0E0E0;
    border-radius: 3px;
    background: #FFFFFF;
}
QCheckBox::indicator:checked {
    background-color: #E55A28;
    border-color: #E55A28;
    image: none;
}
QCheckBox::indicator:hover { border-color: #E55A28; }

/* ── Line Edit / Spin ─────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF;
    border: 1.5px solid #E0E0E0;
    border-radius: 5px;
    padding: 5px 8px;
    color: #1A1A24;
    selection-background-color: #E55A28;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #E55A28;
    outline: none;
}
QLineEdit:read-only {
    background-color: #F8F9FA;
    color: #8A8A9A;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: #F0F2F5;
    border: none;
    width: 18px;
    border-radius: 2px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #E55A28;
    color: white;
}

/* ── ComboBox ─────────────────────────────────────── */
QComboBox {
    background-color: #FFFFFF;
    border: 1.5px solid #E0E0E0;
    border-radius: 5px;
    padding: 5px 8px;
    color: #1A1A24;
    min-width: 80px;
}
QComboBox:hover { border-color: #CCCCCC; }
QComboBox:focus { border-color: #E55A28; }
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    width: 10px; height: 10px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 5px;
    selection-background-color: #F0F2F5;
    selection-color: #E55A28;
}

/* ── Tab Bar ──────────────────────────────────────── */
QTabBar::tab {
    background: #F0F2F5;
    color: #5A5A6A;
    border: 1px solid #E0E0E0;
    border-bottom: none;
    border-radius: 5px 5px 0 0;
    padding: 6px 14px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #E55A28;
    font-weight: 600;
}
QTabBar::tab:hover { color: #E55A28; }

/* ── GroupBox ─────────────────────────────────────── */
QGroupBox {
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px;
    font-weight: 600;
    color: #1A1A24;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
    color: #E55A28;
}

/* ── Labels ───────────────────────────────────────── */
QLabel {
    color: #1A1A24;
    background: transparent;
}
QLabel[secondary="true"] { color: #5A5A6A; }
QLabel[muted="true"] { color: #8A8A9A; font-size: 11px; }

/* ── Scroll Bars ──────────────────────────────────── */
QScrollBar:vertical {
    background: #F0F2F5;
    width: 10px;
    border-radius: 5px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #CCCCCC;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #E55A28; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: #F0F2F5;
    height: 10px;
    border-radius: 5px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #CCCCCC;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #E55A28; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Status Bar ───────────────────────────────────── */
QStatusBar {
    background-color: #F0F2F5;
    color: #5A5A6A;
    border-top: 1px solid #E0E0E0;
    font-size: 12px;
    padding: 2px 8px;
}
QStatusBar::item { border: none; }

/* ── Text Edit ────────────────────────────────────── */
QTextEdit {
    background-color: #FFFFFF;
    border: 1.5px solid #E0E0E0;
    border-radius: 5px;
    padding: 6px;
    color: #1A1A24;
}
QTextEdit:focus { border-color: #E55A28; }

/* ── List / Tree / Table Widgets ─────────────────── */
QListWidget, QTreeWidget, QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 5px;
    alternate-background-color: #F8F9FA;
    color: #1A1A24;
}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected {
    background-color: #FFF3EF;
    color: #E55A28;
}
QListWidget::item:hover, QTreeWidget::item:hover { background: #F8F9FA; }
QHeaderView::section {
    background-color: #F0F2F5;
    color: #5A5A6A;
    border: none;
    border-right: 1px solid #E0E0E0;
    border-bottom: 1px solid #E0E0E0;
    padding: 4px 8px;
    font-weight: 600;
}

/* ── Splitter ─────────────────────────────────────── */
QSplitter::handle {
    background-color: #E0E0E0;
}
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical { height: 2px; }
QSplitter::handle:hover { background-color: #E55A28; }

/* ── Tooltip ──────────────────────────────────────── */
QToolTip {
    background-color: #1A1A24;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ── Progress Bar ─────────────────────────────────── */
QProgressBar {
    background-color: #F0F2F5;
    border: 1px solid #E0E0E0;
    border-radius: 5px;
    text-align: center;
    color: #1A1A24;
    height: 18px;
}
QProgressBar::chunk {
    background-color: #E55A28;
    border-radius: 5px;
}

/* ── Message Box ──────────────────────────────────── */
QMessageBox {
    background-color: #FFFFFF;
}
QMessageBox QLabel { color: #1A1A24; }

/* ── File Dialog ──────────────────────────────────── */
QFileDialog {
    background-color: #F8F9FA;
}
"""
