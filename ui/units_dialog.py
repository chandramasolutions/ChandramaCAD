"""
ChandramaCAD – Drawing Units Conversion Dialog.
Allows the user to rescale all entities in the document by a unit factor.
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QComboBox,
    QPushButton, QFrame,
)
from PySide6.QtCore import Qt

_BTN_PRIMARY = (
    "QPushButton { background: #E55A28; color: #FFFFFF; border: none; "
    "border-radius: 4px; padding: 6px 18px; font-size: 13px; font-weight: 600; }"
    "QPushButton:hover { background: #CC4D22; }"
)
_BTN_SECONDARY = (
    "QPushButton { background: #FFFFFF; color: #1A1A24; border: 1px solid #E0E0E0; "
    "border-radius: 4px; padding: 6px 18px; font-size: 13px; }"
    "QPushButton:hover { background: #F0F2F5; }"
)

# Conversion factors: 1 <unit> = X mm
_UNIT_TO_MM: dict[str, float] = {
    "mm":   1.0,
    "cm":   10.0,
    "m":    1000.0,
    "inch": 25.4,
    "foot": 304.8,
}


class UnitsDialog(QDialog):
    """
    Convert / rescale all entities in the document from one unit to another.

    After accept(), call:
        dialog.apply(document)
    or read:
        dialog.scale_factor   (float)  – multiply all coordinates by this
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drawing Units")
        self.setModal(True)
        self.setMinimumWidth(340)
        self.setStyleSheet(
            "QDialog { background: #F8F9FA; }"
            "QLabel { color: #1A1A24; font-size: 13px; }"
            "QComboBox { background: #FFFFFF; border: 1px solid #E0E0E0; "
            "border-radius: 3px; padding: 4px 8px; font-size: 13px; color: #1A1A24; }"
            "QDoubleSpinBox { background: #FFFFFF; border: 1px solid #E0E0E0; "
            "border-radius: 3px; padding: 4px 8px; font-size: 13px; color: #1A1A24; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        hdr = QLabel("◆ Drawing Units")
        hdr.setStyleSheet("font-size: 15px; font-weight: 700; color: #E55A28;")
        layout.addWidget(hdr)

        sub = QLabel(
            "Rescale all entities in the document by converting from one\n"
            "unit to another.  ChandramaCAD always works internally in mm."
        )
        sub.setStyleSheet("font-size: 12px; color: #5A5A6A;")
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(sep)

        form = QFormLayout()
        form.setSpacing(10)

        unit_names = list(_UNIT_TO_MM.keys())

        self._from_unit = QComboBox()
        self._from_unit.addItems(unit_names)
        self._from_unit.setCurrentText("mm")
        form.addRow("Current unit (treat as):", self._from_unit)

        self._to_unit = QComboBox()
        self._to_unit.addItems(unit_names)
        self._to_unit.setCurrentText("mm")
        form.addRow("Convert to:", self._to_unit)

        layout.addLayout(form)

        # Scale preview
        self._preview = QLabel("Scale factor:  1.0000 ×")
        self._preview.setStyleSheet(
            "padding: 8px 12px; background: #F0F2F5; border-radius: 4px; "
            "font-size: 13px; color: #E55A28; font-weight: 600;"
        )
        layout.addWidget(self._preview)

        self._from_unit.currentTextChanged.connect(self._update_preview)
        self._to_unit.currentTextChanged.connect(self._update_preview)
        self._update_preview()

        # Note
        note = QLabel(
            "ℹ️  A scale factor of 25.4 converts 1 inch document to mm.\n"
            "    The origin (0,0) is preserved."
        )
        note.setStyleSheet("font-size: 11px; color: #8A8A9A;")
        layout.addWidget(note)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_BTN_SECONDARY)
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("Apply Scale")
        ok_btn.setStyleSheet(_BTN_PRIMARY)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _update_preview(self):
        factor = self.scale_factor
        self._preview.setText(f"Scale factor:  {factor:.6g} ×")

    @property
    def scale_factor(self) -> float:
        """Multiply all coordinates by this to convert from → to."""
        from_mm = _UNIT_TO_MM.get(self._from_unit.currentText(), 1.0)
        to_mm   = _UNIT_TO_MM.get(self._to_unit.currentText(), 1.0)
        if to_mm < 1e-12:
            return 1.0
        return from_mm / to_mm

    def apply(self, document) -> None:
        """
        Rescale all entities in *document* by scale_factor.
        Uses entity.scale(factor, origin=[0,0]) to preserve the origin.
        """
        import numpy as np
        factor = self.scale_factor
        if abs(factor - 1.0) < 1e-9:
            return
        origin = np.array([0.0, 0.0])
        snap = document.begin_operation()
        for entity in document.entities:
            try:
                entity.scale(factor, origin)
            except Exception:
                pass
        document.commit_operation(snap)
