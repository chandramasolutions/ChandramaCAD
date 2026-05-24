from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QPushButton,
    QTabWidget, QWidget, QFrame,
)
from PySide6.QtCore import Qt


_STYLE = (
    "QDialog { background: #F8F9FA; }"
    "QLabel { color: #1A1A24; font-size: 13px; }"
    "QTabWidget::pane { border: 1px solid #E0E0E0; border-radius: 4px; background: #FFFFFF; }"
    "QTabBar::tab { background: #F0F2F5; color: #5A5A6A; padding: 6px 16px; "
    "border: 1px solid #E0E0E0; border-bottom: none; border-radius: 4px 4px 0 0; }"
    "QTabBar::tab:selected { background: #FFFFFF; color: #E55A28; font-weight: 600; }"
    "QSpinBox, QDoubleSpinBox { background: #FFFFFF; border: 1px solid #E0E0E0; "
    "border-radius: 3px; padding: 4px 8px; font-size: 13px; color: #1A1A24; }"
    "QSpinBox:focus, QDoubleSpinBox:focus { border-color: #E55A28; }"
)

_BTN_OK = (
    "QPushButton { background: #E55A28; color: #FFFFFF; border: none; "
    "border-radius: 4px; padding: 6px 20px; font-size: 13px; font-weight: 600; }"
    "QPushButton:hover { background: #CC4D22; }"
)
_BTN_CANCEL = (
    "QPushButton { background: #FFFFFF; color: #1A1A24; border: 1px solid #E0E0E0; "
    "border-radius: 4px; padding: 6px 20px; font-size: 13px; }"
    "QPushButton:hover { background: #F0F2F5; }"
)


def _spin_dbl(mn, mx, val, dec=2, suffix=" mm"):
    s = QDoubleSpinBox()
    s.setRange(mn, mx); s.setDecimals(dec); s.setValue(val)
    if suffix: s.setSuffix(suffix)
    return s


def _spin_int(mn, mx, val):
    s = QSpinBox()
    s.setRange(mn, mx); s.setValue(val)
    return s


def _sep():
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("background: #E0E0E0;"); return f


class ArrayDialog(QDialog):
    """
    Dialog for Rectangular and Circular array.
    After exec() == Accepted, read .mode ('rect' | 'circ') and the
    corresponding parameters.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Array")
        self.setModal(True)
        self.setMinimumWidth(320)
        self.setStyleSheet(_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("Create Array")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #1A1A24;")
        root.addWidget(title)
        root.addWidget(_sep())

        # ── Tabs ───────────────────────────────────────────
        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        # Rectangular tab
        rect_w = QWidget()
        rf = QFormLayout(rect_w)
        rf.setSpacing(8)
        rf.setLabelAlignment(Qt.AlignRight)
        self._r_rows   = _spin_int(1, 1000, 3)
        self._r_cols   = _spin_int(1, 1000, 3)
        self._r_row_sp = _spin_dbl(-10000, 10000, 20.0)
        self._r_col_sp = _spin_dbl(-10000, 10000, 20.0)
        self._r_angle  = _spin_dbl(-360, 360, 0.0, suffix="°")
        rf.addRow("Rows:",       self._r_rows)
        rf.addRow("Columns:",    self._r_cols)
        rf.addRow("Row spacing:", self._r_row_sp)
        rf.addRow("Col spacing:", self._r_col_sp)
        rf.addRow("Array angle:", self._r_angle)
        self._tabs.addTab(rect_w, "⊞  Rectangular")

        # Circular tab
        circ_w = QWidget()
        cf = QFormLayout(circ_w)
        cf.setSpacing(8)
        cf.setLabelAlignment(Qt.AlignRight)
        self._c_count    = _spin_int(2, 1000, 6)
        self._c_cx       = _spin_dbl(-100000, 100000, 0.0)
        self._c_cy       = _spin_dbl(-100000, 100000, 0.0)
        self._c_fill_ang = _spin_dbl(1, 360, 360.0, suffix="°")
        self._c_rotate   = QWidget()
        from PySide6.QtWidgets import QCheckBox
        self._c_rotate_items = QCheckBox("Rotate items")
        self._c_rotate_items.setChecked(True)
        self._c_rotate_items.setStyleSheet("color: #1A1A24; font-size: 13px;")
        cf.addRow("Count:",        self._c_count)
        cf.addRow("Center X:",     self._c_cx)
        cf.addRow("Center Y:",     self._c_cy)
        cf.addRow("Fill angle:",   self._c_fill_ang)
        cf.addRow("",              self._c_rotate_items)
        self._tabs.addTab(circ_w, "⊙  Circular")

        # ── Buttons ────────────────────────────────────────
        root.addWidget(_sep())
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(_BTN_CANCEL)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Create Array")
        ok.setDefault(True)
        ok.setStyleSheet(_BTN_OK)
        ok.clicked.connect(self.accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        root.addLayout(btn_row)

    # ── Result accessors ───────────────────────────────────

    @property
    def mode(self) -> str:
        return "rect" if self._tabs.currentIndex() == 0 else "circ"

    # Rectangular
    @property
    def rows(self) -> int:      return self._r_rows.value()
    @property
    def cols(self) -> int:      return self._r_cols.value()
    @property
    def row_spacing(self) -> float: return self._r_row_sp.value()
    @property
    def col_spacing(self) -> float: return self._r_col_sp.value()
    @property
    def array_angle(self) -> float: return self._r_angle.value()

    # Circular
    @property
    def count(self) -> int:         return self._c_count.value()
    @property
    def center_x(self) -> float:    return self._c_cx.value()
    @property
    def center_y(self) -> float:    return self._c_cy.value()
    @property
    def fill_angle(self) -> float:  return self._c_fill_ang.value()
    @property
    def rotate_items(self) -> bool: return self._c_rotate_items.isChecked()
