from __future__ import annotations
import math
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from core.entities import (
    Entity, LineEntity, PolylineEntity, RectangleEntity,
    CircleEntity, ArcEntity, SplineEntity,
)


class PropertiesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        title = QLabel("PROPERTIES")
        title.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #8A8A9A; "
            "letter-spacing: 1px; padding-bottom: 2px;"
        )
        layout.addWidget(title)

        self._group = QGroupBox()
        self._group.setTitle("No selection")
        self._group.setStyleSheet("QGroupBox::title { color: #E55A28; font-weight: 600; }")
        self._form_layout = QFormLayout()
        self._form_layout.setLabelAlignment(Qt.AlignRight)
        self._form_layout.setSpacing(4)
        self._group.setLayout(self._form_layout)
        layout.addWidget(self._group)
        layout.addStretch()

    def show_entities(self, entities: list[Entity]):
        layout = self._form_layout
        while layout.rowCount() > 0:
            layout.removeRow(0)

        if not entities:
            self._group.setTitle("No selection")
            return

        if len(entities) > 1:
            self._group.setTitle(f"{len(entities)} entities selected")
            self._add_row("Types", ", ".join(sorted({type(e).__name__.replace("Entity", "") for e in entities})))
            return

        e = entities[0]
        type_name = type(e).__name__.replace("Entity", "")
        self._group.setTitle(type_name)

        self._add_row("Layer", e.layer)
        self._add_row("Colour", e.color or "(layer)")

        if isinstance(e, LineEntity):
            self._add_row("Start X", f"{e.start[0]:.3f} mm")
            self._add_row("Start Y", f"{e.start[1]:.3f} mm")
            self._add_row("End X", f"{e.end[0]:.3f} mm")
            self._add_row("End Y", f"{e.end[1]:.3f} mm")
            self._add_row("Length", f"{e.length():.3f} mm")
            angle = math.degrees(math.atan2(
                float(e.end[1] - e.start[1]),
                float(e.end[0] - e.start[0])
            ))
            self._add_row("Angle", f"{angle:.2f}°")

        elif isinstance(e, PolylineEntity):
            self._add_row("Vertices", str(len(e.points)))
            self._add_row("Closed", "Yes" if e.closed else "No")
            length = sum(
                float(np.linalg.norm(e.points[i + 1] - e.points[i]))
                for i in range(len(e.points) - 1)
            )
            self._add_row("Length", f"{length:.3f} mm")

        elif isinstance(e, RectangleEntity):
            x1, y1 = e.corner1
            x2, y2 = e.corner2
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            self._add_row("Width", f"{w:.3f} mm")
            self._add_row("Height", f"{h:.3f} mm")
            self._add_row("Area", f"{w * h:.3f} mm²")

        elif isinstance(e, CircleEntity):
            self._add_row("Center X", f"{e.center[0]:.3f} mm")
            self._add_row("Center Y", f"{e.center[1]:.3f} mm")
            self._add_row("Radius", f"{e.radius:.3f} mm")
            self._add_row("Diameter", f"{e.radius * 2:.3f} mm")
            self._add_row("Circumference", f"{2 * math.pi * e.radius:.3f} mm")

        elif isinstance(e, ArcEntity):
            self._add_row("Center X", f"{e.center[0]:.3f} mm")
            self._add_row("Center Y", f"{e.center[1]:.3f} mm")
            self._add_row("Radius", f"{e.radius:.3f} mm")
            self._add_row("Start °", f"{e.start_angle:.2f}°")
            self._add_row("End °", f"{e.end_angle:.2f}°")
            span = e._angle_span()
            self._add_row("Span", f"{span:.2f}°")
            arc_len = math.pi * e.radius * span / 180.0
            self._add_row("Arc length", f"{arc_len:.3f} mm")

        elif isinstance(e, SplineEntity):
            self._add_row("Control pts", str(len(e.control_points)))

    def _add_row(self, label: str, value: str):
        lbl = QLabel(label + ":")
        lbl.setStyleSheet("color: #5A5A6A; font-size: 12px;")
        val = QLineEdit(value)
        val.setReadOnly(True)
        val.setStyleSheet(
            "background: #F8F9FA; border: 1px solid #E0E0E0; "
            "border-radius: 3px; padding: 2px 6px; font-size: 12px; color: #1A1A24;"
        )
        self._form_layout.addRow(lbl, val)
