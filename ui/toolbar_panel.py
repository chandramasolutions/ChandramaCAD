from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QToolButton, QFrame,
    QSizePolicy, QMenu, QInputDialog, QLabel, QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QAction


# ── Tool data ─────────────────────────────────────────────────
# (icon, tooltip, tool_id)
_DRAW_SOLO = [
    ("╱",  "Line  [L]",          "line"),
    ("⌇",  "Polyline  [P]",      "polyline"),
    ("∿",  "Spline",             "spline"),
    ("□",  "Rectangle  [R]",     "rectangle"),
    ("○",  "Circle  [C]",        "circle"),
    ("⌒",  "Arc  [A]",           "arc"),
    ("·",  "Point  [.]",         "point"),
]

_POLYGON_ITEMS = [
    ("△  Triangle (3)",   3),
    ("⬠  Pentagon (5)",   5),
    ("⬡  Hexagon (6)",    6),
    ("◻  Octagon (8)",    8),
    ("⬟  N-sided…",      None),
]

_ROUND_ITEMS = [
    ("⬭  Ellipse  [E]",      "ellipse"),
    ("◑  Semi-circle",       "semicircle"),
    ("⬮  Groove / Slot",     "groove"),
]

# Modify — always-visible (the 4 most common)
_MODIFY_QUICK = [
    ("✥",  "Move  [M]",         "move"),
    ("⎘",  "Copy  [Ctrl+D]",    "copy_tool"),
    ("↻",  "Rotate  [Q]",       "rotate"),
    ("↔",  "Mirror  [I]",       "mirror"),
]

# Modify — flyout "More"
_MODIFY_MORE = [
    ("⇄  Offset  [O]",     "offset"),
    ("✂  Trim  [T]",       "trim"),
    ("→|  Extend  [X]",    "extend"),
    ("─",                  None),
    ("◡  Fillet  [N]",     "fillet"),
    ("╱╲ Chamfer  [H]",    "chamfer"),
    ("✦  Break  [B]",      "break_pt"),
]

_ARRAY_ITEMS = [
    ("⊞  Rectangular  [Y]",  "array_rect"),
    ("⊙  Circular  [U]",     "array_circ"),
]

# Hotwire — shown as 3 individual buttons
_HOTWIRE_QUICK = [
    ("≋",  "Join Segments  [J]",         "join"),
    ("⇌",  "Reverse Path  [V]",          "reverse"),
    ("⌇→", "Convert to Polyline  [K]",   "to_poly"),
]

# Annotate — flyout
_ANNOTATE_ITEMS = [
    ("A   Text  [Ctrl+T]",                 "text"),
    ("|↔| Linear Dimension  [D]",          "dim_linear"),
    ("⊙R  Radial / Dia Dim  [Shift+D]",   "dim_radial"),
]

# ── Styles ────────────────────────────────────────────────────
_BTN_SIZE    = 38      # px (square)
_BTN_FONT_SZ = 14
_ACTIVE = (
    "QToolButton { background: #E55A28; color: #FFFFFF; "
    "border-radius: 5px; font-size: 14px; border: none; }"
)
_IDLE = (
    "QToolButton { background: transparent; color: #1A1A24; "
    "border-radius: 5px; font-size: 14px; border: none; } "
    "QToolButton:hover { background: #E0E2E6; color: #E55A28; }"
)
_FLYOUT_IDLE = (
    "QToolButton { background: transparent; color: #1A1A24; "
    "border-radius: 5px; font-size: 14px; border: none; "
    "padding-right: 6px; } "
    "QToolButton:hover { background: #E0E2E6; color: #E55A28; } "
    "QToolButton::menu-indicator { image: none; width: 0; }"
)
_FLYOUT_ACTIVE = (
    "QToolButton { background: #E55A28; color: #FFFFFF; "
    "border-radius: 5px; font-size: 14px; border: none; padding-right: 6px; } "
    "QToolButton::menu-indicator { image: none; width: 0; }"
)
_MENU_STYLE = (
    "QMenu { background: #FFFFFF; border: 1px solid #E0E0E0; "
    "border-radius: 6px; padding: 4px 0; }"
    "QMenu::item { padding: 7px 22px 7px 12px; color: #1A1A24; font-size: 13px; }"
    "QMenu::item:selected { background: #F0F2F5; color: #E55A28; }"
    "QMenu::separator { height: 1px; background: #E0E0E0; margin: 3px 8px; }"
)
_GRP_LABEL = (
    "color: #8A8A9A; font-size: 7px; font-weight: 700; "
    "letter-spacing: 0.8px; padding: 0;"
)


# ═════════════════════════════════════════════════════════════
class ToolbarPanel(QWidget):
    """Horizontal top toolbar with labelled category groups."""

    tool_selected    = Signal(str)
    polygon_sides    = Signal(int)
    zoom_in_clicked  = Signal()
    zoom_out_clicked = Signal()
    fit_clicked      = Signal()
    scale_clicked    = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setObjectName("ToolbarPanel")
        self.setStyleSheet(
            "#ToolbarPanel { background: #F0F2F5; "
            "border-bottom: 2px solid #E0E0E0; }"
        )

        self._buttons: dict[str, QToolButton] = {}
        self._active_tool = "select"
        self._btn_font    = QFont("Segoe UI", _BTN_FONT_SZ)

        # Horizontal scroll so narrow windows work
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; } "
            "QScrollBar:horizontal { height: 6px; background: #E0E0E0; } "
            "QScrollBar::handle:horizontal { background: #C0C0C0; border-radius: 3px; }"
        )

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._row = QHBoxLayout(container)
        self._row.setContentsMargins(8, 4, 8, 4)
        self._row.setSpacing(0)
        self._row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # ── SELECT ────────────────────────────────────────────
        sel_btn = self._solo_btn("↖", "Select  [Esc]", "select")
        self._add_group("SELECT", [sel_btn])
        self._row.addWidget(self._vsep())

        # ── DRAW ──────────────────────────────────────────────
        draw_btns = []
        for icon, tip, tid in _DRAW_SOLO:
            draw_btns.append(self._solo_btn(icon, tip, tid))
        draw_btns.append(self._polygon_flyout())
        draw_btns.append(self._round_flyout())
        self._add_group("DRAW", draw_btns)
        self._row.addWidget(self._vsep())

        # ── MODIFY ────────────────────────────────────────────
        mod_btns = []
        for icon, tip, tid in _MODIFY_QUICK:
            mod_btns.append(self._solo_btn(icon, tip, tid))
        mod_btns.append(self._menu_flyout("…", "More modify tools", _MODIFY_MORE))
        self._add_group("MODIFY", mod_btns)
        self._row.addWidget(self._vsep())

        # ── ARRAY ─────────────────────────────────────────────
        arr_btns = [self._menu_flyout("⊞", "Array", _ARRAY_ITEMS)]
        for _, tid in _ARRAY_ITEMS:
            self._buttons[tid] = arr_btns[0]
        self._add_group("ARRAY", arr_btns)
        self._row.addWidget(self._vsep())

        # ── HOTWIRE ───────────────────────────────────────────
        hw_btns = []
        for icon, tip, tid in _HOTWIRE_QUICK:
            hw_btns.append(self._solo_btn(icon, tip, tid))
        self._add_group("HOTWIRE", hw_btns)
        self._row.addWidget(self._vsep())

        # ── ANNOTATE ──────────────────────────────────────────
        ann_btns = [self._menu_flyout("◈", "Annotate", _ANNOTATE_ITEMS)]
        for _, tid in _ANNOTATE_ITEMS:
            self._buttons[tid] = ann_btns[0]
        self._add_group("ANNOTATE", ann_btns)
        self._row.addWidget(self._vsep())

        # ── VIEW ──────────────────────────────────────────────
        sc_btn = self._make_btn("⇲", "Scale selection  [Alt+S]")
        sc_btn.clicked.connect(self.scale_clicked)

        zi = self._make_btn("⊕", "Zoom In  [+]")
        zi.clicked.connect(self.zoom_in_clicked)
        zo = self._make_btn("⊖", "Zoom Out  [−]")
        zo.clicked.connect(self.zoom_out_clicked)
        fit = self._make_btn("⤢", "Fit to Screen  [F]")
        fit.clicked.connect(self.fit_clicked)

        self._add_group("VIEW", [sc_btn, zi, zo, fit])
        self._row.addStretch()

        scroll.setWidget(container)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._set_active("select")

    # ── Group builder ──────────────────────────────────────────

    def _add_group(self, name: str, buttons: list[QToolButton]):
        """Add a labelled group of buttons to the main row."""
        grp = QWidget()
        grp.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(grp)
        vbox.setContentsMargins(4, 0, 4, 0)
        vbox.setSpacing(0)

        # Category label
        lbl = QLabel(name)
        lbl.setStyleSheet(_GRP_LABEL)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(10)
        vbox.addWidget(lbl)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 1, 0, 1)
        btn_row.setSpacing(1)
        for b in buttons:
            btn_row.addWidget(b)
        vbox.addLayout(btn_row)

        self._row.addWidget(grp)

    # ── Button factories ───────────────────────────────────────

    def _make_btn(self, icon: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(icon)
        btn.setFont(self._btn_font)
        btn.setToolTip(tip)
        btn.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        btn.setStyleSheet(_IDLE)
        return btn

    def _solo_btn(self, icon: str, tip: str, tool_id: str) -> QToolButton:
        btn = self._make_btn(icon, tip)
        btn.clicked.connect(lambda _=False, t=tool_id: self._on_tool(t))
        self._buttons[tool_id] = btn
        return btn

    def _polygon_flyout(self) -> QToolButton:
        btn = self._make_btn("⬡", "Polygons (triangle, pentagon, hexagon…)")
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setStyleSheet(_FLYOUT_IDLE)
        menu = QMenu(btn)
        menu.setStyleSheet(_MENU_STYLE)
        for label, n in _POLYGON_ITEMS:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, ns=n: self._on_polygon(ns))
            menu.addAction(act)
        btn.setMenu(menu)
        self._buttons["polygon"] = btn
        return btn

    def _round_flyout(self) -> QToolButton:
        btn = self._make_btn("⊙", "Circle variants (ellipse, semi-circle, groove)")
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setStyleSheet(_FLYOUT_IDLE)
        menu = QMenu(btn)
        menu.setStyleSheet(_MENU_STYLE)
        for label, tid in _ROUND_ITEMS:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, t=tid: self._on_tool(t))
            menu.addAction(act)
        btn.setMenu(menu)
        for _, tid in _ROUND_ITEMS:
            self._buttons[tid] = btn
        return btn

    def _menu_flyout(self, icon: str, tip: str,
                     items: list[tuple[str, str | None]]) -> QToolButton:
        """Generic flyout button whose menu items emit tool_selected."""
        btn = self._make_btn(icon, tip)
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setStyleSheet(_FLYOUT_IDLE)
        menu = QMenu(btn)
        menu.setStyleSheet(_MENU_STYLE)
        for label, tid in items:
            if label == "─":
                menu.addSeparator()
            else:
                act = QAction(label, self)
                act.triggered.connect(lambda _=False, t=tid: self._on_tool(t))
                menu.addAction(act)
                if tid:
                    self._buttons[tid] = btn
        btn.setMenu(menu)
        return btn

    # ── Separators ────────────────────────────────────────────

    def _vsep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setFixedHeight(46)
        sep.setStyleSheet("background: #D8D8DC; margin: 0 4px;")
        return sep

    # ── Activation ────────────────────────────────────────────

    def _set_active(self, tool_id: str):
        for tid, btn in self._buttons.items():
            is_active = (tid == tool_id)
            # Use flyout style when the button is a flyout (has a menu)
            if btn.popupMode() == QToolButton.InstantPopup:
                btn.setStyleSheet(_FLYOUT_ACTIVE if is_active else _FLYOUT_IDLE)
            else:
                btn.setStyleSheet(_ACTIVE if is_active else _IDLE)
        self._active_tool = tool_id

    def _on_tool(self, tool_id: str):
        self._set_active(tool_id)
        self.tool_selected.emit(tool_id)

    def _on_polygon(self, n_sides):
        if n_sides is None:
            val, ok = QInputDialog.getInt(
                self, "N-sided Polygon", "Number of sides:", 7, 3, 360, 1)
            if not ok:
                return
            n_sides = val
        self.polygon_sides.emit(n_sides)
        icons = {3: "△", 5: "⬠", 6: "⬡", 8: "◻"}
        self._buttons["polygon"].setText(icons.get(n_sides, "⬟"))
        self._set_active("polygon")
        self.tool_selected.emit("polygon")

    # ── Public API ─────────────────────────────────────────────

    def set_active_tool(self, tool_id: str):
        self._set_active(tool_id)
