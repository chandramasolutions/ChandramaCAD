from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QToolButton, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


TOOLS = [
    ("select",    "↖",  "Select (Esc)"),
    ("line",      "╱",  "Line (L)"),
    ("polyline",  "⌇",  "Polyline (P)"),
    ("rectangle", "□",  "Rectangle (R)"),
    ("circle",    "○",  "Circle (C)"),
    ("arc",       "⌒",  "Arc (A)"),
    ("spline",    "~",  "Spline (S)"),
]

ZOOM_ACTIONS = [
    ("zoom_in",   "⊕",  "Zoom In (+)"),
    ("zoom_out",  "⊖",  "Zoom Out (-)"),
    ("fit",       "⤢",  "Fit to Screen (F)"),
]


class ToolbarPanel(QWidget):
    tool_selected = Signal(str)
    zoom_in_clicked = Signal()
    zoom_out_clicked = Signal()
    fit_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(52)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setObjectName("ToolbarPanel")
        self.setStyleSheet("#ToolbarPanel { background: #F0F2F5; border-right: 1px solid #E0E0E0; }")

        self._buttons: dict[str, QToolButton] = {}
        self._active_tool = "select"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignTop)

        font = QFont("Segoe UI", 14)

        for tool_id, icon, tooltip in TOOLS:
            btn = self._make_button(icon, tooltip, font)
            btn.clicked.connect(lambda checked=False, tid=tool_id: self._on_tool_clicked(tid))
            self._buttons[tool_id] = btn
            layout.addWidget(btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E0E0E0; margin: 4px 0;")
        layout.addWidget(sep)

        # Zoom actions
        for action_id, icon, tooltip in ZOOM_ACTIONS:
            btn = self._make_button(icon, tooltip, font)
            if action_id == "zoom_in":
                btn.clicked.connect(self.zoom_in_clicked)
            elif action_id == "zoom_out":
                btn.clicked.connect(self.zoom_out_clicked)
            elif action_id == "fit":
                btn.clicked.connect(self.fit_clicked)
            layout.addWidget(btn)

        layout.addStretch()
        self._set_active("select")

    def _make_button(self, icon: str, tooltip: str, font: QFont) -> QToolButton:
        btn = QToolButton()
        btn.setText(icon)
        btn.setFont(font)
        btn.setToolTip(tooltip)
        btn.setFixedSize(44, 44)
        btn.setCheckable(False)
        return btn

    def _on_tool_clicked(self, tool_id: str):
        self._set_active(tool_id)
        self.tool_selected.emit(tool_id)

    def _set_active(self, tool_id: str):
        for tid, btn in self._buttons.items():
            if tid == tool_id:
                btn.setStyleSheet(
                    "QToolButton { background: #E55A28; color: white; "
                    "border-radius: 6px; font-size: 16px; }"
                )
            else:
                btn.setStyleSheet(
                    "QToolButton { background: transparent; color: #1A1A24; "
                    "border-radius: 6px; font-size: 16px; }"
                    "QToolButton:hover { background: #E8E8E8; color: #E55A28; }"
                )
        self._active_tool = tool_id

    def set_active_tool(self, tool_id: str):
        self._set_active(tool_id)
