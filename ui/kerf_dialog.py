"""
ChandramaCAD – Kerf Compensation & GCode Export Dialog.
Collects wire diameter, feedrate, and kerf side before GCode export.
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QComboBox,
    QPushButton, QFrame, QGroupBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

_BTN_PRIMARY = (
    "QPushButton { background: #E55A28; color: #FFFFFF; border: none; "
    "border-radius: 4px; padding: 6px 18px; font-size: 13px; font-weight: 600; }"
    "QPushButton:hover { background: #CC4D22; }"
    "QPushButton:disabled { background: #CCCCCC; }"
)
_BTN_SECONDARY = (
    "QPushButton { background: #FFFFFF; color: #1A1A24; border: 1px solid #E0E0E0; "
    "border-radius: 4px; padding: 6px 18px; font-size: 13px; }"
    "QPushButton:hover { background: #F0F2F5; }"
)
_SPIN_STYLE = (
    "QDoubleSpinBox, QSpinBox { background: #FFFFFF; border: 1px solid #E0E0E0; "
    "border-radius: 3px; padding: 4px 8px; font-size: 13px; color: #1A1A24; }"
    "QDoubleSpinBox:focus, QSpinBox:focus { border-color: #E55A28; }"
)


class KerfDialog(QDialog):
    """
    Collects hotwire cutting parameters:
      - Wire diameter (mm) → kerf = diameter / 2
      - Feed rate (mm/min)
      - Rapid traverse rate (mm/min)
      - Wire-on command (M3/M8/custom)
      - Wire-off command (M5/M9/custom)

    After accept(), read:
      dialog.kerf_mm          (float)
      dialog.feedrate          (float)
      dialog.rapid_feedrate    (float)
      dialog.wire_on_cmd       (str)
      dialog.wire_off_cmd      (str)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hotwire GCode Settings")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setStyleSheet(
            "QDialog { background: #F8F9FA; }"
            "QLabel { color: #1A1A24; font-size: 13px; }"
            "QGroupBox { font-size: 12px; font-weight: 700; color: #5A5A6A; "
            "border: 1px solid #E0E0E0; border-radius: 4px; margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
            + _SPIN_STYLE
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Header ─────────────────────────────────────────
        hdr = QLabel("◆ Hotwire GCode Export")
        hdr.setStyleSheet("font-size: 15px; font-weight: 700; color: #E55A28;")
        layout.addWidget(hdr)

        sub = QLabel("Configure kerf compensation and cutting parameters.")
        sub.setStyleSheet("font-size: 12px; color: #5A5A6A;")
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(sep)

        # ── Kerf group ─────────────────────────────────────
        kerf_grp = QGroupBox("Kerf Compensation")
        kerf_form = QFormLayout(kerf_grp)
        kerf_form.setContentsMargins(10, 16, 10, 10)
        kerf_form.setSpacing(8)

        self._wire_diam = QDoubleSpinBox()
        self._wire_diam.setRange(0.0, 20.0)
        self._wire_diam.setDecimals(3)
        self._wire_diam.setSingleStep(0.1)
        self._wire_diam.setValue(0.5)
        self._wire_diam.setSuffix(" mm")
        self._wire_diam.setToolTip(
            "Hot wire diameter.  Kerf = diameter ÷ 2.\n"
            "Set 0 to disable kerf compensation."
        )
        kerf_form.addRow("Wire diameter:", self._wire_diam)

        self._kerf_lbl = QLabel("→ Kerf offset: 0.250 mm")
        self._kerf_lbl.setStyleSheet("color: #E55A28; font-size: 12px; font-style: italic;")
        kerf_form.addRow("", self._kerf_lbl)
        self._wire_diam.valueChanged.connect(self._update_kerf_label)
        self._update_kerf_label()

        layout.addWidget(kerf_grp)

        # ── Feed rates group ─────────────────────────────────
        feed_grp = QGroupBox("Feed Rates")
        feed_form = QFormLayout(feed_grp)
        feed_form.setContentsMargins(10, 16, 10, 10)
        feed_form.setSpacing(8)

        self._feedrate = QDoubleSpinBox()
        self._feedrate.setRange(10.0, 30000.0)
        self._feedrate.setDecimals(0)
        self._feedrate.setSingleStep(100.0)
        self._feedrate.setValue(1000.0)
        self._feedrate.setSuffix(" mm/min")
        feed_form.addRow("Cutting feed:", self._feedrate)

        self._rapid = QDoubleSpinBox()
        self._rapid.setRange(10.0, 30000.0)
        self._rapid.setDecimals(0)
        self._rapid.setSingleStep(500.0)
        self._rapid.setValue(3000.0)
        self._rapid.setSuffix(" mm/min")
        feed_form.addRow("Rapid traverse:", self._rapid)

        layout.addWidget(feed_grp)

        # ── Commands group ───────────────────────────────────
        cmd_grp = QGroupBox("Wire Commands")
        cmd_form = QFormLayout(cmd_grp)
        cmd_form.setContentsMargins(10, 16, 10, 10)
        cmd_form.setSpacing(8)

        self._wire_on = QComboBox()
        self._wire_on.addItems(["M3", "M8", "M3 S255"])
        self._wire_on.setStyleSheet(
            "QComboBox { background: #FFFFFF; border: 1px solid #E0E0E0; "
            "border-radius: 3px; padding: 4px 8px; font-size: 13px; color: #1A1A24; }"
        )
        cmd_form.addRow("Wire ON:", self._wire_on)

        self._wire_off = QComboBox()
        self._wire_off.addItems(["M5", "M9"])
        self._wire_off.setStyleSheet(self._wire_on.styleSheet())
        cmd_form.addRow("Wire OFF:", self._wire_off)

        layout.addWidget(cmd_grp)

        # ── Buttons ──────────────────────────────────────────
        layout.addSpacing(4)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_BTN_SECONDARY)
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("Export GCode…")
        ok_btn.setStyleSheet(_BTN_PRIMARY)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _update_kerf_label(self):
        kerf = self._wire_diam.value() / 2.0
        self._kerf_lbl.setText(f"→ Kerf offset: {kerf:.3f} mm")

    # ── Public result properties ─────────────────────────────

    @property
    def kerf_mm(self) -> float:
        return self._wire_diam.value() / 2.0

    @property
    def feedrate(self) -> float:
        return self._feedrate.value()

    @property
    def rapid_feedrate(self) -> float:
        return self._rapid.value()

    @property
    def wire_on_cmd(self) -> str:
        return self._wire_on.currentText()

    @property
    def wire_off_cmd(self) -> str:
        return self._wire_off.currentText()
