from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QPushButton, QRadioButton,
    QButtonGroup, QGroupBox, QFrame,
)
from PySide6.QtCore import Qt


class ScaleDialog(QDialog):
    """Dialog to get scale factor and pivot point for geometry scaling."""

    def __init__(self, has_selection: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scale Geometry")
        self.setModal(True)
        self.setMinimumWidth(300)
        self.setStyleSheet(
            "QDialog { background: #F8F9FA; }"
            "QLabel { color: #1A1A24; font-size: 13px; }"
            "QGroupBox { color: #5A5A6A; font-size: 12px; font-weight: 600; "
            "border: 1px solid #E0E0E0; border-radius: 4px; margin-top: 8px; padding-top: 4px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
            "QRadioButton { color: #1A1A24; font-size: 13px; }"
            "QDoubleSpinBox { background: #FFFFFF; border: 1px solid #E0E0E0; "
            "border-radius: 3px; padding: 4px 8px; font-size: 13px; color: #1A1A24; }"
            "QDoubleSpinBox:focus { border-color: #E55A28; }"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Title label ────────────────────────────────────
        title = QLabel("Scale Geometry")
        title.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #1A1A24;"
        )
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: #E0E0E0;")
        layout.addWidget(sep)

        # ── Scale factor ───────────────────────────────────
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._factor_spin = QDoubleSpinBox()
        self._factor_spin.setRange(0.001, 10000.0)
        self._factor_spin.setDecimals(4)
        self._factor_spin.setValue(1.0)
        self._factor_spin.setSuffix("×")
        self._factor_spin.setStepType(QDoubleSpinBox.AdaptiveDecimalStepType)

        factor_lbl = QLabel("Scale factor:")
        factor_lbl.setStyleSheet("color: #5A5A6A; font-size: 13px;")
        form.addRow(factor_lbl, self._factor_spin)
        layout.addLayout(form)

        # Quick-select buttons
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        for label, val in [("½×", 0.5), ("2×", 2.0), ("5×", 5.0), ("10×", 10.0)]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "QPushButton { background: #FFFFFF; color: #E55A28; "
                "border: 1px solid #E55A28; border-radius: 4px; "
                "padding: 3px 10px; font-size: 12px; }"
                "QPushButton:hover { background: #E55A28; color: #FFFFFF; }"
            )
            btn.clicked.connect(lambda _=False, v=val: self._factor_spin.setValue(v))
            quick_row.addWidget(btn)
        layout.addLayout(quick_row)

        # ── Pivot point ────────────────────────────────────
        pivot_group = QGroupBox("Pivot point")
        pivot_layout = QVBoxLayout(pivot_group)
        pivot_layout.setSpacing(4)

        self._pivot_selection = QRadioButton("Selection center")
        self._pivot_origin    = QRadioButton("World origin (0, 0)")

        if has_selection:
            self._pivot_selection.setChecked(True)
        else:
            self._pivot_origin.setChecked(True)
            self._pivot_selection.setEnabled(False)

        self._pivot_group = QButtonGroup(self)
        self._pivot_group.addButton(self._pivot_selection, 0)
        self._pivot_group.addButton(self._pivot_origin, 1)

        pivot_layout.addWidget(self._pivot_selection)
        pivot_layout.addWidget(self._pivot_origin)
        layout.addWidget(pivot_group)

        # ── Buttons ────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #1A1A24; "
            "border: 1px solid #E0E0E0; border-radius: 4px; padding: 6px 20px; font-size: 13px; }"
            "QPushButton:hover { background: #F0F2F5; }"
        )
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton("Apply Scale")
        apply_btn.setDefault(True)
        apply_btn.setStyleSheet(
            "QPushButton { background: #E55A28; color: #FFFFFF; "
            "border: none; border-radius: 4px; padding: 6px 20px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #CC4D22; }"
        )
        apply_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

    @property
    def factor(self) -> float:
        return self._factor_spin.value()

    @property
    def pivot_is_selection_center(self) -> bool:
        return self._pivot_group.checkedId() == 0
