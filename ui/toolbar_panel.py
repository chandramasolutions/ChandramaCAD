from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QToolButton, QFrame, QSizePolicy,
    QMenu, QInputDialog, QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QAction


# ── Standalone tool definitions ─────────────────────────
_TOOLS = [
    ("select",    "↖",  "Select  [Esc]"),
]

_LINE_TOOLS = [
    ("line",      "╱",  "Line  [L]"),
    ("polyline",  "⌇",  "Polyline  [P]"),
    ("spline",    "∿",  "Spline"),
]

_SHAPE_TOOLS = [
    ("rectangle", "□",  "Rectangle  [R]"),
    ("circle",    "○",  "Circle  [C]"),
    ("arc",       "⌒",  "Arc  [A]"),
]

_ZOOM_ACTIONS = [
    ("zoom_in",   "⊕",  "Zoom In  [+]"),
    ("zoom_out",  "⊖",  "Zoom Out  [−]"),
    ("fit",       "⤢",  "Fit to Screen  [F]"),
]

# Polygon sub-tools: (label shown in menu, tool-id, n_sides or None for custom)
_POLYGON_ITEMS = [
    ("△  Triangle (3 sides)",  "polygon", 3),
    ("⬠  Pentagon (5 sides)",  "polygon", 5),
    ("⬡  Hexagon (6 sides)",   "polygon", 6),
    ("□□ Octagon (8 sides)",   "polygon", 8),
    ("⬟  N-sided…",            "polygon", None),
]

# Circle-variant sub-tools
_ROUND_ITEMS = [
    ("⬭  Ellipse",       "ellipse",    None),
    ("◑  Semi-circle",   "semicircle", None),
    ("⬮  Groove / Slot", "groove",     None),
]

_BTN_STYLE = (
    "QToolButton {{ background: {bg}; color: {fg}; "
    "border-radius: 6px; font-size: 16px; border: none; }}"
    "QToolButton:hover {{ background: #E8E8E8; color: #E55A28; }}"
)
_BTN_ACTIVE = "QToolButton { background: #E55A28; color: #FFFFFF; border-radius: 6px; font-size: 16px; }"
_BTN_IDLE   = "QToolButton { background: transparent; color: #1A1A24; border-radius: 6px; font-size: 16px; } " \
              "QToolButton:hover { background: #E8E8E8; color: #E55A28; }"

_MENU_STYLE = (
    "QMenu { background: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 6px; padding: 4px 0; }"
    "QMenu::item { padding: 7px 18px 7px 12px; color: #1A1A24; font-size: 13px; }"
    "QMenu::item:selected { background: #F0F2F5; color: #E55A28; }"
)


class ToolbarPanel(QWidget):
    tool_selected   = Signal(str)      # emits tool id, e.g. "line", "polygon", "ellipse"
    polygon_sides   = Signal(int)      # emits n_sides whenever a polygon variant is chosen
    zoom_in_clicked  = Signal()
    zoom_out_clicked = Signal()
    fit_clicked      = Signal()
    scale_clicked    = Signal()        # emits when Scale action is triggered

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(58)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setObjectName("ToolbarPanel")
        self.setStyleSheet(
            "#ToolbarPanel { background: #F0F2F5; border-right: 1px solid #E0E0E0; }"
        )

        self._buttons: dict[str, QToolButton] = {}
        self._active_tool = "select"

        # Scroll area so all buttons fit regardless of window height
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignTop)

        font = QFont("Segoe UI", 14)

        # ── Selection ──────────────────────────────────────
        for tid, icon, tip in _TOOLS:
            btn = self._make_btn(icon, tip, font)
            btn.clicked.connect(lambda _=False, t=tid: self._on_tool(t))
            self._buttons[tid] = btn
            layout.addWidget(btn)

        layout.addWidget(self._separator())

        # ── Lines / curves ─────────────────────────────────
        for tid, icon, tip in _LINE_TOOLS:
            btn = self._make_btn(icon, tip, font)
            btn.clicked.connect(lambda _=False, t=tid: self._on_tool(t))
            self._buttons[tid] = btn
            layout.addWidget(btn)

        layout.addWidget(self._separator())

        # ── Primitive shapes ───────────────────────────────
        for tid, icon, tip in _SHAPE_TOOLS:
            btn = self._make_btn(icon, tip, font)
            btn.clicked.connect(lambda _=False, t=tid: self._on_tool(t))
            self._buttons[tid] = btn
            layout.addWidget(btn)

        layout.addWidget(self._separator())

        # ── Polygons group ─────────────────────────────────
        self._poly_btn = self._make_btn("⬡", "Polygons (triangle, pentagon, hexagon…)", font)
        self._poly_btn.setPopupMode(QToolButton.InstantPopup)
        poly_menu = QMenu(self._poly_btn)
        poly_menu.setStyleSheet(_MENU_STYLE)
        for label, tid, n_sides in _POLYGON_ITEMS:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, t=tid, n=n_sides: self._on_polygon(t, n))
            poly_menu.addAction(act)
        self._poly_btn.setMenu(poly_menu)
        self._buttons["polygon"] = self._poly_btn
        layout.addWidget(self._poly_btn)

        layout.addWidget(self._separator())

        # ── Circle variants group ──────────────────────────
        self._round_btn = self._make_btn("⊙", "Circle variants (ellipse, semi-circle, groove)", font)
        self._round_btn.setPopupMode(QToolButton.InstantPopup)
        round_menu = QMenu(self._round_btn)
        round_menu.setStyleSheet(_MENU_STYLE)
        for label, tid, _ in _ROUND_ITEMS:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, t=tid: self._on_tool(t))
            round_menu.addAction(act)
        self._round_btn.setMenu(round_menu)
        # Register under each variant id so highlight works
        for _, tid, _ in _ROUND_ITEMS:
            self._buttons[tid] = self._round_btn
        layout.addWidget(self._round_btn)

        layout.addWidget(self._separator())

        # ── Actions ────────────────────────────────────────
        scale_btn = self._make_btn("⇲", "Scale selection  [Alt+S]", font)
        scale_btn.clicked.connect(self.scale_clicked)
        layout.addWidget(scale_btn)

        layout.addWidget(self._separator())

        # ── View controls ──────────────────────────────────
        for action_id, icon, tip in _ZOOM_ACTIONS:
            btn = self._make_btn(icon, tip, font)
            if action_id == "zoom_in":
                btn.clicked.connect(self.zoom_in_clicked)
            elif action_id == "zoom_out":
                btn.clicked.connect(self.zoom_out_clicked)
            else:
                btn.clicked.connect(self.fit_clicked)
            layout.addWidget(btn)

        layout.addStretch()

        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._set_active("select")

    # ── Internal helpers ───────────────────────────────────

    def _make_btn(self, icon: str, tip: str, font: QFont) -> QToolButton:
        btn = QToolButton()
        btn.setText(icon)
        btn.setFont(font)
        btn.setToolTip(tip)
        btn.setFixedSize(50, 46)
        btn.setStyleSheet(_BTN_IDLE)
        return btn

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #E0E0E0; margin: 3px 4px;")
        return sep

    def _set_active(self, tool_id: str):
        for tid, btn in self._buttons.items():
            if tid == tool_id:
                btn.setStyleSheet(_BTN_ACTIVE)
            else:
                btn.setStyleSheet(_BTN_IDLE)
        self._active_tool = tool_id

    def _on_tool(self, tool_id: str):
        self._set_active(tool_id)
        self.tool_selected.emit(tool_id)

    def _on_polygon(self, tool_id: str, n_sides):
        if n_sides is None:
            # Ask user for number of sides
            val, ok = QInputDialog.getInt(
                self, "N-sided Polygon", "Number of sides:", 7, 3, 360, 1
            )
            if not ok:
                return
            n_sides = val
        self.polygon_sides.emit(n_sides)
        # Update polygon button label to show selected shape
        icons = {3: "△", 5: "⬠", 6: "⬡", 8: "◻"}
        self._poly_btn.setText(icons.get(n_sides, "⬟"))
        self._set_active(tool_id)
        self.tool_selected.emit(tool_id)

    # ── Public API ─────────────────────────────────────────

    def set_active_tool(self, tool_id: str):
        self._set_active(tool_id)
