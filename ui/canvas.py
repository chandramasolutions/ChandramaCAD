from __future__ import annotations
import math
import copy
import numpy as np
from typing import Optional
from PySide6.QtWidgets import QWidget, QApplication, QInputDialog
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, Signal, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPixmap,
    QPainterPath, QPolygonF, QKeyEvent, QMouseEvent, QWheelEvent,
)
from core.document import Document
from core.entities import (
    Entity, LineEntity, PolylineEntity, RectangleEntity,
    CircleEntity, ArcEntity, SplineEntity,
    PolygonEntity, EllipseEntity, SemiCircleEntity, GrooveEntity,
    PointEntity, TextEntity, DimLinearEntity, DimRadialEntity,
)
from core.snap_engine import SnapEngine, SnapResult
from core.intersect import (
    mirror_point, offset_polyline, offset_segment,
    line_line_intersect, seg_seg_intersect,
    circle_line_t, t_values_on_line,
    fillet_lines, chamfer_lines,
)


# ── Tool mode constants ───────────────────────────────────────
TOOL_SELECT     = "select"
TOOL_LINE       = "line"
TOOL_POLYLINE   = "polyline"
TOOL_RECTANGLE  = "rectangle"
TOOL_CIRCLE     = "circle"
TOOL_ARC        = "arc"
TOOL_SPLINE     = "spline"
TOOL_POLYGON    = "polygon"
TOOL_ELLIPSE    = "ellipse"
TOOL_SEMICIRCLE = "semicircle"
TOOL_GROOVE     = "groove"
TOOL_POINT      = "point"

# Modify tools
TOOL_MOVE       = "move"
TOOL_COPY_TOOL  = "copy_tool"
TOOL_ROTATE     = "rotate"
TOOL_MIRROR     = "mirror"
TOOL_OFFSET     = "offset"
TOOL_TRIM       = "trim"
TOOL_EXTEND     = "extend"
TOOL_FILLET     = "fillet"
TOOL_CHAMFER    = "chamfer"
TOOL_BREAK      = "break_pt"

# Annotation tools
TOOL_TEXT       = "text"
TOOL_DIM_LINEAR = "dim_linear"
TOOL_DIM_RADIAL = "dim_radial"

# Axis colours
_X_COLOR      = QColor("#C04444")
_Y_COLOR      = QColor("#2266BB")
_ORIGIN_COLOR = QColor("#555555")
_DIM_COLOR    = QColor("#6644AA")


# ── Image overlay ─────────────────────────────────────────────
class ImageOverlay:
    """Reference image placed in world coordinates for tracing."""
    def __init__(self, pixmap: QPixmap, path: str,
                 world_x: float, world_y: float,
                 world_w: float, world_h: float,
                 opacity: float = 0.5):
        self.pixmap   = pixmap
        self.path     = path
        self.world_x  = float(world_x)
        self.world_y  = float(world_y)
        self.world_w  = float(world_w)
        self.world_h  = float(world_h)
        self.opacity  = max(0.05, min(1.0, float(opacity)))
        self.visible  = True
        self.locked   = False
        self.selected = False


# ═════════════════════════════════════════════════════════════
class Canvas(QWidget):
    entity_added      = Signal(object)
    selection_changed = Signal(list)
    cursor_moved      = Signal(float, float)
    zoom_changed      = Signal(float)
    tool_changed      = Signal(str)
    status_hint       = Signal(str)       # per-step instruction for the status bar

    def __init__(self, document: Document, snap_engine: SnapEngine, parent=None):
        super().__init__(parent)
        self.document    = document
        self.snap_engine = snap_engine

        # View
        self._scale: float = 5.0
        self._pan_offset   = QPointF(0.0, 0.0)
        self._initialized  = False

        # Grid / axes
        self.grid_visible: bool = True
        self.axes_visible: bool = True
        self.grid_size: float   = 10.0

        # Images
        self._images: list[ImageOverlay]        = []
        self._dragging_image: Optional[ImageOverlay] = None
        self._drag_img_offset: np.ndarray       = np.zeros(2)

        # Tool state — drawing
        self._tool: str              = TOOL_SELECT
        self._tool_points: list[np.ndarray] = []
        self._polygon_sides: int     = 6

        # Arc (3-click)
        self._arc_step: int          = 0
        self._arc_center: Optional[np.ndarray] = None
        self._arc_radius: float      = 0.0
        self._arc_start_angle: float = 0.0

        # Groove (3-click)
        self._groove_step: int = 0
        self._groove_c1: Optional[np.ndarray] = None
        self._groove_c2: Optional[np.ndarray] = None

        # Tool state — modify
        self._mod_step: int = 0
        self._mod_base:  Optional[np.ndarray] = None   # Move/Copy base point
        self._mod_ref_angle: float = 0.0               # Rotate reference angle
        self._mod_entity: Optional[Entity] = None      # Offset / Trim / Extend / Fillet / Chamfer hit

        # Dimension tool
        self._dim_step: int = 0
        self._dim_p1:   Optional[np.ndarray] = None
        self._dim_p2:   Optional[np.ndarray] = None

        # Snap / cursor
        self._snap_result: Optional[SnapResult] = None
        self._cursor_world = np.zeros(2)

        # Pan (middle-mouse or Space+drag)
        self._panning = False
        self._space_held: bool = False
        self._pan_start_px: Optional[QPoint]   = None
        self._pan_start_offset: Optional[QPointF] = None

        # Rubber-band
        self._rubber_start_px: Optional[QPoint] = None
        self._rubber_end_px:   Optional[QPoint] = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.ArrowCursor)

    # ── Lifecycle ─────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            self._pan_offset  = QPointF(self.width() / 2.0, self.height() / 2.0)
            self._initialized = True

    # ── Public API ────────────────────────────────────────────

    # Step-by-step hint shown in status bar for every tool
    _TOOL_HINTS = {
        TOOL_SELECT:     "Click to select · Drag to box-select · Shift+Click to add",
        TOOL_LINE:       "Line ▶ click start point",
        TOOL_POLYLINE:   "Polyline ▶ click points · Right-click / Enter to finish",
        TOOL_RECTANGLE:  "Rectangle ▶ click first corner",
        TOOL_CIRCLE:     "Circle ▶ click centre",
        TOOL_ARC:        "Arc ▶ click centre  (3 clicks: centre → start → end)",
        TOOL_SPLINE:     "Spline ▶ click control points · Right-click / Enter to finish",
        TOOL_POLYGON:    "Polygon ▶ click centre",
        TOOL_ELLIPSE:    "Ellipse ▶ click first corner of bounding box",
        TOOL_SEMICIRCLE: "Semi-circle ▶ click centre",
        TOOL_GROOVE:     "Groove ▶ click first centre  (3 clicks: c1 → c2 → radius)",
        TOOL_POINT:      "Point ▶ click to place",
        TOOL_MOVE:       "Move ▶ click base point  (select entities first, or click entity)",
        TOOL_COPY_TOOL:  "Copy ▶ click base point  (select entities first, or click entity)",
        TOOL_ROTATE:     "Rotate ▶ click pivot  (select entities first)",
        TOOL_MIRROR:     "Mirror ▶ click axis start  (select entities first)",
        TOOL_OFFSET:     "Offset ▶ click entity to offset",
        TOOL_TRIM:       "Trim ▶ click segment to remove",
        TOOL_EXTEND:     "Extend ▶ click line to extend · then click boundary",
        TOOL_FILLET:     "Fillet ▶ click first line",
        TOOL_CHAMFER:    "Chamfer ▶ click first line",
        TOOL_BREAK:      "Break ▶ click entity at break point",
        TOOL_TEXT:       "Text ▶ click insertion point",
        TOOL_DIM_LINEAR: "Linear Dim ▶ click first point",
        TOOL_DIM_RADIAL: "Radial Dim ▶ click a circle or arc",
    }

    def set_tool(self, tool: str):
        self._cancel_tool()
        self._tool = tool
        self.setCursor(Qt.ArrowCursor if tool == TOOL_SELECT else Qt.CrossCursor)
        self.tool_changed.emit(tool)
        self.status_hint.emit(self._TOOL_HINTS.get(tool, ""))
        self.update()

    def set_polygon_sides(self, n: int):
        self._polygon_sides = max(3, n)

    def center_origin(self):
        self._pan_offset = QPointF(self.width() / 2.0, self.height() / 2.0)
        self._scale      = 5.0
        self.zoom_changed.emit(self._scale)
        self.update()

    def fit_to_screen(self):
        entities = self.document.visible_entities()
        if not entities:
            self.center_origin(); return
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for e in entities:
            bb = e.bounding_box()
            min_x = min(min_x, bb[0]); min_y = min(min_y, bb[1])
            max_x = max(max_x, bb[2]); max_y = max(max_y, bb[3])
        if max_x <= min_x: max_x = min_x + 10
        if max_y <= min_y: max_y = min_y + 10
        margin  = 0.12
        w_world = (max_x - min_x) * (1 + 2 * margin)
        h_world = (max_y - min_y) * (1 + 2 * margin)
        self._scale = min(self.width() / w_world, self.height() / h_world)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self._pan_offset = QPointF(
            self.width()  / 2 - cx * self._scale,
            self.height() / 2 + cy * self._scale,
        )
        self.zoom_changed.emit(self._scale)
        self.update()

    # ── Image management ──────────────────────────────────────

    def add_image(self, path: str, world_x: float, world_y: float,
                  world_w: float, world_h: float, opacity: float = 0.5) -> ImageOverlay:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            raise ValueError(f"Cannot load image: {path}")
        overlay = ImageOverlay(pixmap, path, world_x, world_y, world_w, world_h, opacity)
        self._images.append(overlay)
        self.update()
        return overlay

    def remove_selected_images(self):
        self._images = [img for img in self._images if not img.selected]
        self.update()

    def selected_images(self) -> list[ImageOverlay]:
        return [img for img in self._images if img.selected]

    # ── Instant operations (called from main_window) ──────────

    def op_join(self, tolerance: float = 0.5):
        """Merge endpoint-connected selected entities into polylines."""
        selected = self.document.selected_entities()
        if len(selected) < 2:
            return

        # Collect all segments as (start, end, entity)
        def endpoints(e: Entity):
            if isinstance(e, LineEntity):
                return e.start.copy(), e.end.copy()
            elif isinstance(e, PolylineEntity):
                return e.points[0].copy(), e.points[-1].copy()
            elif isinstance(e, SplineEntity) and e.control_points:
                return e.control_points[0].copy(), e.control_points[-1].copy()
            return None, None

        # Build adjacency
        remaining = list(selected)
        chains: list[list[np.ndarray]] = []

        while remaining:
            # Start a new chain with first remaining
            seed = remaining.pop(0)
            s, e_pt = endpoints(seed)
            if s is None:
                continue
            chain_pts = list(seed.to_points(64))
            chain_closed = False

            changed = True
            while changed:
                changed = False
                for ent in list(remaining):
                    ep_s, ep_e = endpoints(ent)
                    if ep_s is None:
                        continue
                    cur_s = np.array(chain_pts[0])
                    cur_e = np.array(chain_pts[-1])
                    ent_pts = list(ent.to_points(64))
                    if np.linalg.norm(cur_e - ep_s) < tolerance:
                        chain_pts = chain_pts + ent_pts[1:]
                        remaining.remove(ent); changed = True
                    elif np.linalg.norm(cur_e - ep_e) < tolerance:
                        chain_pts = chain_pts + list(reversed(ent_pts))[1:]
                        remaining.remove(ent); changed = True
                    elif np.linalg.norm(cur_s - ep_e) < tolerance:
                        chain_pts = ent_pts + chain_pts[1:]
                        remaining.remove(ent); changed = True
                    elif np.linalg.norm(cur_s - ep_s) < tolerance:
                        chain_pts = list(reversed(ent_pts)) + chain_pts[1:]
                        remaining.remove(ent); changed = True

            chains.append(chain_pts)

        if not chains:
            return

        snap = self.document.begin_operation()
        ids = [e.id for e in selected]
        self.document.entities = [e for e in self.document.entities if e.id not in ids]
        for chain_pts in chains:
            pts = [np.array(p) for p in chain_pts]
            if len(pts) >= 2:
                poly = PolylineEntity(pts)
                poly.layer = self.document.active_layer
                self.document.entities.append(poly)
        self.document.commit_operation(snap)
        self.document.deselect_all()
        self.selection_changed.emit([])
        self.entity_added.emit(None)
        self.update()

    def op_reverse(self):
        """Reverse direction of selected polylines / splines / lines."""
        selected = self.document.selected_entities()
        if not selected:
            return
        snap = self.document.begin_operation()
        for e in selected:
            if isinstance(e, PolylineEntity):
                e.points = list(reversed(e.points))
            elif isinstance(e, SplineEntity):
                e.control_points = list(reversed(e.control_points))
            elif isinstance(e, LineEntity):
                e.start, e.end = e.end.copy(), e.start.copy()
        self.document.commit_operation(snap)
        self.update()

    def op_to_polyline(self, segments: int = 200):
        """Convert selected entities to polylines (discretise curves)."""
        selected = self.document.selected_entities()
        if not selected:
            return
        snap = self.document.begin_operation()
        ids = [e.id for e in selected]
        new_entities = []
        for e in selected:
            pts = e.to_points(segments)
            if len(pts) >= 2:
                poly = PolylineEntity([np.array(p) for p in pts])
                poly.layer = e.layer
                poly.color = e.color
                new_entities.append(poly)
        self.document.entities = [e for e in self.document.entities if e.id not in ids]
        for ne in new_entities:
            self.document.entities.append(ne)
        self.document.commit_operation(snap)
        self.document.deselect_all()
        self.selection_changed.emit([])
        self.entity_added.emit(None)
        self.update()

    def op_array_rect(self, rows: int, cols: int,
                      row_spacing: float, col_spacing: float,
                      angle_deg: float = 0.0):
        """Rectangular array of selected entities."""
        selected = self.document.selected_entities()
        if not selected:
            return
        snap = self.document.begin_operation()
        ang = math.radians(angle_deg)
        cos_a, sin_a = math.cos(ang), math.sin(ang)
        for r in range(rows):
            for c in range(cols):
                if r == 0 and c == 0:
                    continue
                dx_w = c * col_spacing
                dy_w = r * row_spacing
                # Rotate offset by array angle
                dx = dx_w * cos_a - dy_w * sin_a
                dy = dx_w * sin_a + dy_w * cos_a
                for e in selected:
                    clone = e.clone()
                    clone.translate(float(dx), float(dy))
                    clone.selected = False
                    self.document.entities.append(clone)
        self.document.commit_operation(snap)
        self.entity_added.emit(None)
        self.update()

    def op_array_circ(self, count: int, center: np.ndarray,
                      fill_angle: float = 360.0, rotate_items: bool = True):
        """Circular array of selected entities."""
        selected = self.document.selected_entities()
        if not selected or count < 2:
            return
        snap = self.document.begin_operation()
        step = fill_angle / (count if abs(fill_angle - 360) < 0.01 else count - 1)
        for i in range(1, count):
            angle = step * i
            for e in selected:
                clone = e.clone()
                clone.rotate(angle, center)
                if not rotate_items:
                    # Undo the rotation of the entity itself, keep only position change
                    clone.rotate(-angle, center)
                    bb = e.bounding_box()
                    cx_e = (bb[0] + bb[2]) / 2
                    cy_e = (bb[1] + bb[3]) / 2
                    rad_e = math.radians(angle)
                    new_cx = center[0] + (cx_e - center[0]) * math.cos(rad_e) \
                                       - (cy_e - center[1]) * math.sin(rad_e)
                    new_cy = center[1] + (cx_e - center[0]) * math.sin(rad_e) \
                                       + (cy_e - center[1]) * math.cos(rad_e)
                    clone.translate(float(new_cx - cx_e), float(new_cy - cy_e))
                clone.selected = False
                self.document.entities.append(clone)
        self.document.commit_operation(snap)
        self.entity_added.emit(None)
        self.update()

    # ── Coordinate transforms ─────────────────────────────────

    def world_to_screen(self, wx: float, wy: float) -> QPointF:
        return QPointF(
            wx * self._scale + self._pan_offset.x(),
            -wy * self._scale + self._pan_offset.y(),
        )

    def screen_to_world(self, sx: float, sy: float) -> np.ndarray:
        return np.array([
            (sx - self._pan_offset.x()) / self._scale,
            -(sy - self._pan_offset.y()) / self._scale,
        ])

    # ── Paint ─────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        if self.grid_visible:
            self._draw_grid(painter)

        self._draw_images(painter)

        if self.axes_visible:
            self._draw_origin_axes(painter)

        for entity in self.document.visible_entities():
            self._draw_entity(painter, entity)

        for entity in self.document.selected_entities():
            self._draw_selection_handles(painter, entity)

        self._draw_tool_preview(painter)

        if self._snap_result and self._snap_result.snap_type != "none":
            self._draw_snap_indicator(painter, self._snap_result.point)

        if self._rubber_start_px and self._rubber_end_px:
            self._draw_rubber_band(painter)

        painter.end()

    # ── Grid ──────────────────────────────────────────────────

    def _draw_grid(self, painter: QPainter):
        gs = self.grid_size
        pen_min = QPen(QColor("#F0F0F0"), 0.5)
        pen_maj = QPen(QColor("#E4E4E4"), 0.8)

        left_w  = self.screen_to_world(0, 0)[0]
        right_w = self.screen_to_world(self.width(), 0)[0]
        top_w   = self.screen_to_world(0, 0)[1]
        bot_w   = self.screen_to_world(0, self.height())[1]

        x = math.floor(left_w / gs) * gs
        while x <= right_w:
            painter.setPen(pen_maj if round(x / gs) % 10 == 0 else pen_min)
            painter.drawLine(self.world_to_screen(x, top_w), self.world_to_screen(x, bot_w))
            x += gs

        y = math.floor(bot_w / gs) * gs
        while y <= top_w:
            painter.setPen(pen_maj if round(y / gs) % 10 == 0 else pen_min)
            painter.drawLine(self.world_to_screen(left_w, y), self.world_to_screen(right_w, y))
            y += gs

    # ── Images ────────────────────────────────────────────────

    def _draw_images(self, painter: QPainter):
        for img in self._images:
            if not img.visible:
                continue
            tl = self.world_to_screen(img.world_x, img.world_y)
            br = self.world_to_screen(img.world_x + img.world_w,
                                      img.world_y  - img.world_h)
            w_px = int(abs(br.x() - tl.x()))
            h_px = int(abs(br.y() - tl.y()))
            if w_px < 1 or h_px < 1:
                continue

            target = QRect(int(tl.x()), int(tl.y()), w_px, h_px)
            painter.setOpacity(img.opacity)
            painter.drawPixmap(target, img.pixmap)
            painter.setOpacity(1.0)

            if img.selected:
                frect = QRectF(tl, br)
                sel_pen = QPen(QColor("#E55A28"), 1.8, Qt.DashLine)
                sel_pen.setCosmetic(True)
                painter.setPen(sel_pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(frect)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#E55A28"))
                for corner in (frect.topLeft(), frect.topRight(),
                               frect.bottomLeft(), frect.bottomRight()):
                    painter.drawRect(QRectF(corner.x() - 5, corner.y() - 5, 10, 10))
                import os as _os
                painter.setPen(QColor("#E55A28"))
                painter.setFont(QFont("Segoe UI", 8))
                painter.drawText(QPointF(tl.x() + 4, tl.y() + 14),
                                 _os.path.basename(img.path))

    # ── Origin axes ───────────────────────────────────────────

    def _draw_origin_axes(self, painter: QPainter):
        sw, sh = float(self.width()), float(self.height())
        ARROW  = 12.0
        font   = QFont("Segoe UI", 8, QFont.Bold)

        origin_s = self.world_to_screen(0.0, 0.0)
        ox, oy   = origin_s.x(), origin_s.y()

        if 0 <= oy <= sh:
            pen = QPen(_X_COLOR, 1.5); pen.setCosmetic(True)
            painter.setPen(pen); painter.setBrush(Qt.NoBrush)
            painter.drawLine(QPointF(0.0, oy), QPointF(sw, oy))
            tip = QPointF(sw - 2, oy)
            painter.setPen(Qt.NoPen); painter.setBrush(_X_COLOR)
            painter.drawPolygon(QPolygonF([
                tip,
                QPointF(sw - 2 - ARROW, oy - ARROW * 0.4),
                QPointF(sw - 2 - ARROW, oy + ARROW * 0.4),
            ]))
            painter.setFont(font); painter.setPen(_X_COLOR)
            painter.drawText(QPointF(sw - 2 - ARROW - 26, oy - 5), "+X")
            self._draw_x_ticks(painter, oy, sw, sh)

        if 0 <= ox <= sw:
            pen = QPen(_Y_COLOR, 1.5); pen.setCosmetic(True)
            painter.setPen(pen); painter.setBrush(Qt.NoBrush)
            painter.drawLine(QPointF(ox, 0.0), QPointF(ox, sh))
            tip = QPointF(ox, 2.0)
            painter.setPen(Qt.NoPen); painter.setBrush(_Y_COLOR)
            painter.drawPolygon(QPolygonF([
                tip,
                QPointF(ox - ARROW * 0.4, 2.0 + ARROW),
                QPointF(ox + ARROW * 0.4, 2.0 + ARROW),
            ]))
            painter.setFont(font); painter.setPen(_Y_COLOR)
            painter.drawText(QPointF(ox + 5, 2.0 + ARROW + 14), "+Y")
            self._draw_y_ticks(painter, ox, sw, sh)

        if 0 <= ox <= sw and 0 <= oy <= sh:
            painter.setPen(QPen(_ORIGIN_COLOR, 1.2))
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(origin_s, 4.5, 4.5)
            if oy > 16 and ox < sw - 36:
                painter.setPen(_ORIGIN_COLOR)
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(QPointF(ox + 6, oy - 4), "(0, 0)")

    def _nice_interval(self, visible_range: float) -> float:
        if visible_range <= 0:
            return 1.0
        raw = visible_range / 8.0
        if raw <= 0:
            return 1.0
        mag = 10 ** math.floor(math.log10(raw))
        for m in (1, 2, 5, 10):
            if m * mag >= raw:
                return m * mag
        return mag * 10

    def _draw_x_ticks(self, painter: QPainter, axis_y: float, sw: float, sh: float):
        left_w  = self.screen_to_world(0, 0)[0]
        right_w = self.screen_to_world(sw, 0)[0]
        tick    = self._nice_interval(right_w - left_w)
        painter.setFont(QFont("Segoe UI", 7))
        x = math.floor(left_w / tick) * tick
        while x <= right_w:
            if abs(x) > tick * 0.01:
                sx = self.world_to_screen(x, 0).x()
                if 4 <= sx <= sw - 40:
                    painter.setPen(QPen(_X_COLOR, 1.0))
                    painter.drawLine(QPointF(sx, axis_y - 3), QPointF(sx, axis_y + 3))
                    painter.setPen(_X_COLOR)
                    painter.drawText(QPointF(sx - 14, axis_y + 14), f"{x:.4g}")
            x += tick

    def _draw_y_ticks(self, painter: QPainter, axis_x: float, sw: float, sh: float):
        bot_w = self.screen_to_world(0, sh)[1]
        top_w = self.screen_to_world(0, 0)[1]
        tick  = self._nice_interval(top_w - bot_w)
        painter.setFont(QFont("Segoe UI", 7))
        y = math.floor(bot_w / tick) * tick
        while y <= top_w:
            if abs(y) > tick * 0.01:
                sy = self.world_to_screen(0, y).y()
                if 20 <= sy <= sh - 10:
                    painter.setPen(QPen(_Y_COLOR, 1.0))
                    painter.drawLine(QPointF(axis_x - 3, sy), QPointF(axis_x + 3, sy))
                    painter.setPen(_Y_COLOR)
                    painter.drawText(QPointF(axis_x + 5, sy + 4), f"{y:.4g}")
            y += tick

    # ── Entity drawing ────────────────────────────────────────

    def _draw_entity(self, painter: QPainter, entity: Entity):
        layer     = self.document.get_layer(entity.layer)
        color_str = entity.color or (layer.color if layer else "#1A1A24")
        color     = QColor(color_str)

        if isinstance(entity, DimLinearEntity):
            self._draw_dim_linear(painter, entity)
            return
        if isinstance(entity, DimRadialEntity):
            self._draw_dim_radial(painter, entity)
            return

        pen = QPen(color, 2.0 if entity.selected else 1.2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if isinstance(entity, PointEntity):
            sp = self.world_to_screen(float(entity.position[0]), float(entity.position[1]))
            sz = 5.0
            painter.drawLine(QPointF(sp.x() - sz, sp.y()), QPointF(sp.x() + sz, sp.y()))
            painter.drawLine(QPointF(sp.x(), sp.y() - sz), QPointF(sp.x(), sp.y() + sz))
            painter.drawEllipse(sp, 2.5, 2.5)

        elif isinstance(entity, TextEntity):
            sp  = self.world_to_screen(float(entity.position[0]), float(entity.position[1]))
            h_px = max(6.0, entity.height * self._scale)
            font = QFont("Segoe UI", int(h_px))
            painter.setFont(font)
            painter.save()
            painter.translate(sp)
            painter.rotate(-entity.rotation_deg)
            painter.drawText(QPointF(0, 0), entity.text)
            painter.restore()

        elif isinstance(entity, LineEntity):
            painter.drawLine(self.world_to_screen(*entity.start),
                             self.world_to_screen(*entity.end))

        elif isinstance(entity, CircleEntity):
            c = self.world_to_screen(*entity.center)
            painter.drawEllipse(c, entity.radius * self._scale,
                                    entity.radius * self._scale)

        elif isinstance(entity, EllipseEntity):
            c  = self.world_to_screen(*entity.center)
            rx = entity.rx * self._scale
            ry = entity.ry * self._scale
            if abs(entity.rotation_deg) > 0.01:
                painter.save()
                painter.translate(c)
                painter.rotate(-entity.rotation_deg)
                painter.drawEllipse(QPointF(0, 0), rx, ry)
                painter.restore()
            else:
                painter.drawEllipse(c, rx, ry)

        elif isinstance(entity, (ArcEntity, SemiCircleEntity)):
            pts = entity.to_points(64)
            if len(pts) < 2: return
            path = QPainterPath()
            path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
            for p in pts[1:]: path.lineTo(self.world_to_screen(p[0], p[1]))
            painter.drawPath(path)

        elif isinstance(entity, (PolylineEntity, RectangleEntity, SplineEntity,
                                  PolygonEntity, GrooveEntity)):
            pts = entity.to_points()
            if len(pts) < 2: return
            path = QPainterPath()
            path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
            for p in pts[1:]: path.lineTo(self.world_to_screen(p[0], p[1]))
            closed = isinstance(entity, (RectangleEntity, PolygonEntity, GrooveEntity)) or \
                     (isinstance(entity, PolylineEntity) and entity.closed)
            if closed:
                path.closeSubpath()
            painter.drawPath(path)

    def _draw_dim_linear(self, painter: QPainter, entity: DimLinearEntity):
        """Draw a linear dimension with extension lines, arrows and text."""
        p1, p2 = entity.p1, entity.p2
        d = p2 - p1
        length = float(np.linalg.norm(d))
        if length < 1e-10:
            return

        perp = np.array([-d[1], d[0]]) / length  # unit perpendicular (left)
        off = entity.offset

        # Offset points in world space
        op1 = p1 + perp * off
        op2 = p2 + perp * off

        op1s = self.world_to_screen(float(op1[0]), float(op1[1]))
        op2s = self.world_to_screen(float(op2[0]), float(op2[1]))
        p1s  = self.world_to_screen(float(p1[0]), float(p1[1]))
        p2s  = self.world_to_screen(float(p2[0]), float(p2[1]))

        color = QColor(_DIM_COLOR) if not entity.color else QColor(entity.color)
        ext_pen = QPen(color, 0.8, Qt.DotLine); ext_pen.setCosmetic(True)
        dim_pen = QPen(color, 1.4); dim_pen.setCosmetic(True)

        # Extension lines
        painter.setPen(ext_pen)
        painter.drawLine(p1s, op1s)
        painter.drawLine(p2s, op2s)

        # Dimension line
        painter.setPen(dim_pen)
        painter.drawLine(op1s, op2s)

        # Arrows
        ARROW = 7.0
        dl = math.hypot(op2s.x() - op1s.x(), op2s.y() - op1s.y())
        if dl > 1e-6:
            ux = (op2s.x() - op1s.x()) / dl
            uy = (op2s.y() - op1s.y()) / dl
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            for tip, sgn in [(op1s, 1.0), (op2s, -1.0)]:
                painter.drawPolygon(QPolygonF([
                    tip,
                    QPointF(tip.x() + sgn * ux * ARROW - uy * ARROW * 0.35,
                            tip.y() + sgn * uy * ARROW + ux * ARROW * 0.35),
                    QPointF(tip.x() + sgn * ux * ARROW + uy * ARROW * 0.35,
                            tip.y() + sgn * uy * ARROW - ux * ARROW * 0.35),
                ]))

        # Measurement text
        mid = QPointF((op1s.x() + op2s.x()) / 2, (op1s.y() + op2s.y()) / 2)
        text = f"{entity.measurement():.2f}"
        painter.setPen(color)
        painter.setFont(QFont("Segoe UI", 8))
        angle_deg = math.degrees(math.atan2(op2s.y() - op1s.y(), op2s.x() - op1s.x()))
        painter.save()
        painter.translate(mid)
        painter.rotate(angle_deg)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text)
        painter.drawText(QPointF(-tw / 2, -4), text)
        painter.restore()

    def _draw_dim_radial(self, painter: QPainter, entity: DimRadialEntity):
        """Draw a radial/diameter dimension leader."""
        cs  = self.world_to_screen(float(entity.center[0]), float(entity.center[1]))
        rad = math.radians(entity.angle_deg)
        r_px = entity.radius * self._scale

        tip_x = cs.x() + math.cos(rad) * r_px
        tip_y = cs.y() - math.sin(rad) * r_px   # screen Y is flipped
        tip   = QPointF(tip_x, tip_y)

        ext   = 18.0   # leader extension (px)
        text_pt = QPointF(tip_x + math.cos(rad) * ext,
                          tip_y - math.sin(rad) * ext)

        color = QColor(_DIM_COLOR) if not entity.color else QColor(entity.color)
        pen   = QPen(color, 1.4); pen.setCosmetic(True)
        painter.setPen(pen); painter.setBrush(Qt.NoBrush)

        # If diameter: draw through center
        if entity.is_diameter:
            opp = QPointF(cs.x() - math.cos(rad) * r_px,
                          cs.y() + math.sin(rad) * r_px)
            painter.drawLine(opp, tip)
        else:
            painter.drawLine(cs, tip)

        painter.drawLine(tip, text_pt)

        prefix = "⌀" if entity.is_diameter else "R"
        val    = entity.radius * 2 if entity.is_diameter else entity.radius
        text   = f"{prefix}{val:.2f}"
        painter.setPen(color)
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QPointF(text_pt.x() + 2, text_pt.y() + 4), text)

    # ── Selection handles ─────────────────────────────────────

    def _draw_selection_handles(self, painter: QPainter, entity: Entity):
        pen = QPen(QColor("#E55A28"), 1.5); pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor("#E55A28"))
        sz = 7

        def handle(world_pt):
            sp = self.world_to_screen(float(world_pt[0]), float(world_pt[1]))
            painter.drawRect(int(sp.x()) - sz // 2, int(sp.y()) - sz // 2, sz, sz)

        if isinstance(entity, PointEntity):
            handle(entity.position)
        elif isinstance(entity, (TextEntity, DimLinearEntity)):
            pass
        elif isinstance(entity, DimRadialEntity):
            handle(entity.center)
        elif isinstance(entity, LineEntity):
            handle(entity.start); handle(entity.end)
        elif isinstance(entity, PolylineEntity):
            for p in entity.points: handle(p)
        elif isinstance(entity, RectangleEntity):
            for c in entity._corners: handle(c)
        elif isinstance(entity, CircleEntity):
            handle(entity.center)
            handle(entity.center + np.array([entity.radius, 0]))
        elif isinstance(entity, ArcEntity):
            handle(entity.center)
            pts = entity.to_points(32)
            handle(pts[0]); handle(pts[-1])
        elif isinstance(entity, SplineEntity):
            for cp in entity.control_points: handle(cp)
        elif isinstance(entity, PolygonEntity):
            handle(entity.center)
            for v in entity._vertices(): handle(v)
        elif isinstance(entity, EllipseEntity):
            handle(entity.center)
        elif isinstance(entity, SemiCircleEntity):
            handle(entity.center)
            pts = entity._arc_points(16)
            handle(pts[0]); handle(pts[-1])
        elif isinstance(entity, GrooveEntity):
            handle(entity.center1); handle(entity.center2)

    # ── Tool preview ──────────────────────────────────────────

    def _draw_tool_preview(self, painter: QPainter):
        dash_pen = QPen(QColor("#E55A28"), 1.5, Qt.DashLine)
        dash_pen.setCosmetic(True)
        cur = self._snap_result.point if self._snap_result else self._cursor_world
        t   = self._tool

        # ── Dot markers for every committed intermediate point ──────────
        dot_pen = QPen(QColor("#E55A28"), 1.5)
        dot_pen.setCosmetic(True)
        dot_brush = QBrush(QColor("#E55A28"))
        blue_pen   = QPen(QColor("#2266BB"), 1.5)
        blue_pen.setCosmetic(True)
        blue_brush = QBrush(QColor("#2266BB"))
        dim_brush  = QBrush(_DIM_COLOR)

        def _dot(pt, pen=dot_pen, brush=dot_brush, r=4.5):
            sp = self.world_to_screen(float(pt[0]), float(pt[1]))
            painter.setPen(pen)
            painter.setBrush(brush)
            painter.drawEllipse(sp, r, r)

        for pt in self._tool_points:
            _dot(pt)
        if self._arc_center is not None:
            _dot(self._arc_center)
        if self._groove_c1 is not None:
            _dot(self._groove_c1)
        if self._groove_c2 is not None:
            _dot(self._groove_c2)
        if self._mod_base is not None:
            _dot(self._mod_base, blue_pen, blue_brush)
        if self._dim_p1 is not None:
            _dot(self._dim_p1, QPen(_DIM_COLOR, 1.5), dim_brush)
        if self._dim_p2 is not None:
            _dot(self._dim_p2, QPen(_DIM_COLOR, 1.5), dim_brush)

        # ── Dashed preview geometry ─────────────────────────────────────
        painter.setPen(dash_pen)
        painter.setBrush(Qt.NoBrush)

        # ── Drawing tools ─────────────────────────────────
        if t == TOOL_LINE and self._tool_points:
            painter.drawLine(self.world_to_screen(*self._tool_points[0]),
                             self.world_to_screen(*cur))

        elif t == TOOL_POLYLINE and self._tool_points:
            for i in range(len(self._tool_points) - 1):
                painter.drawLine(self.world_to_screen(*self._tool_points[i]),
                                 self.world_to_screen(*self._tool_points[i + 1]))
            painter.drawLine(self.world_to_screen(*self._tool_points[-1]),
                             self.world_to_screen(*cur))

        elif t in (TOOL_RECTANGLE, TOOL_ELLIPSE) and self._tool_points:
            p1 = self.world_to_screen(*self._tool_points[0])
            p2 = self.world_to_screen(*cur)
            x  = min(p1.x(), p2.x()); y = min(p1.y(), p2.y())
            w  = abs(p2.x() - p1.x()); h = abs(p2.y() - p1.y())
            if t == TOOL_RECTANGLE:
                painter.drawRect(int(x), int(y), int(w), int(h))
            else:
                painter.drawEllipse(QPointF(x + w / 2, y + h / 2), w / 2, h / 2)

        elif t == TOOL_CIRCLE and self._tool_points:
            c  = self.world_to_screen(*self._tool_points[0])
            c2 = self.world_to_screen(*cur)
            r  = math.hypot(c2.x() - c.x(), c2.y() - c.y())
            painter.drawEllipse(c, r, r)

        elif t == TOOL_ARC:
            if self._arc_step == 1 and self._arc_center is not None:
                painter.drawLine(self.world_to_screen(*self._arc_center),
                                 self.world_to_screen(*cur))
            elif self._arc_step == 2 and self._arc_center is not None:
                ea = math.degrees(math.atan2(float(cur[1] - self._arc_center[1]),
                                             float(cur[0] - self._arc_center[0]))) % 360
                dummy = ArcEntity(self._arc_center, self._arc_radius,
                                  self._arc_start_angle, ea)
                self._draw_pts_path(painter, dummy.to_points(32))

        elif t == TOOL_SPLINE and self._tool_points:
            dummy = SplineEntity(self._tool_points + [cur])
            pts   = dummy.to_points()
            if len(pts) > 1:
                self._draw_pts_path(painter, pts)
            else:
                painter.drawLine(self.world_to_screen(*self._tool_points[0]),
                                 self.world_to_screen(*cur))

        elif t == TOOL_POLYGON and self._tool_points:
            center = self._tool_points[0]
            r = float(np.linalg.norm(cur - center))
            if r > 1e-6:
                rot   = math.degrees(math.atan2(float(cur[1]-center[1]),
                                                float(cur[0]-center[0])))
                dummy = PolygonEntity(center, self._polygon_sides, r, rot)
                self._draw_pts_path(painter, dummy.to_points(), closed=True)

        elif t == TOOL_SEMICIRCLE and self._tool_points:
            center = self._tool_points[0]
            r = float(np.linalg.norm(cur - center))
            if r > 1e-6:
                bump  = math.degrees(math.atan2(float(cur[1]-center[1]),
                                                float(cur[0]-center[0])))
                dummy = SemiCircleEntity(center, r, (bump - 90) % 360)
                self._draw_pts_path(painter, dummy.to_points(32))

        elif t == TOOL_GROOVE:
            if self._groove_step == 1 and self._groove_c1 is not None:
                painter.drawLine(self.world_to_screen(*self._groove_c1),
                                 self.world_to_screen(*cur))
            elif self._groove_step == 2 and self._groove_c1 and self._groove_c2:
                axis = self._groove_c2 - self._groove_c1
                aln  = float(np.linalg.norm(axis))
                if aln > 1e-6:
                    perp = np.array([-axis[1], axis[0]]) / aln
                    mid  = (self._groove_c1 + self._groove_c2) / 2
                    r    = max(abs(float(np.dot(cur - mid, perp))), 0.5)
                    dummy = GrooveEntity(self._groove_c1, self._groove_c2, r)
                    self._draw_pts_path(painter, dummy.to_points(32))

        # ── Modify tools ──────────────────────────────────
        elif t in (TOOL_MOVE, TOOL_COPY_TOOL) and self._mod_step == 1 \
                and self._mod_base is not None:
            delta = cur - self._mod_base
            painter.setOpacity(0.55)
            for e in self.document.selected_entities():
                clone = e.clone()
                clone.translate(float(delta[0]), float(delta[1]))
                self._draw_entity(painter, clone)
            painter.setOpacity(1.0)
            # Show delta
            painter.setPen(QPen(QColor("#E55A28"), 1.0, Qt.DotLine))
            painter.drawLine(self.world_to_screen(*self._mod_base),
                             self.world_to_screen(*cur))
            painter.setPen(QColor("#E55A28"))
            painter.setFont(QFont("Segoe UI", 8))
            ps = self.world_to_screen(*cur)
            painter.drawText(QPointF(ps.x() + 6, ps.y() - 6),
                             f"Δ {float(delta[0]):.2f}, {float(delta[1]):.2f}")

        elif t == TOOL_ROTATE and self._mod_step == 1 \
                and self._mod_base is not None:
            pivot = self._mod_base
            cur_ang = math.degrees(math.atan2(float(cur[1] - pivot[1]),
                                              float(cur[0] - pivot[0])))
            rotation = cur_ang - self._mod_ref_angle
            pivot_s  = self.world_to_screen(*pivot)
            cur_s    = self.world_to_screen(*cur)
            painter.setPen(QPen(QColor("#E55A28"), 1.0, Qt.DotLine))
            painter.drawLine(pivot_s, cur_s)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(pivot_s, 6, 6)
            painter.setOpacity(0.55)
            for e in self.document.selected_entities():
                clone = e.clone()
                clone.rotate(rotation, pivot)
                self._draw_entity(painter, clone)
            painter.setOpacity(1.0)
            painter.setPen(QColor("#E55A28"))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(QPointF(pivot_s.x() + 10, pivot_s.y() - 10),
                             f"{rotation:.1f}°")

        elif t == TOOL_MIRROR and self._mod_step == 1 \
                and self._mod_base is not None:
            axis_p1 = self._mod_base
            axis_p2 = cur
            axis_s1  = self.world_to_screen(*axis_p1)
            axis_s2  = self.world_to_screen(*axis_p2)
            painter.setPen(QPen(QColor("#2266BB"), 1.0, Qt.DotLine))
            painter.drawLine(axis_s1, axis_s2)
            if float(np.linalg.norm(axis_p2 - axis_p1)) > 1e-6:
                painter.setOpacity(0.55)
                for e in self.document.selected_entities():
                    clone = e.clone()
                    self._mirror_entity(clone, axis_p1, axis_p2)
                    self._draw_entity(painter, clone)
                painter.setOpacity(1.0)

        elif t == TOOL_OFFSET and self._mod_step == 1 \
                and self._mod_entity is not None:
            e     = self._mod_entity
            dist  = self._offset_distance(e, cur)
            clone = self._compute_offset(e, dist)
            if clone is not None:
                painter.setOpacity(0.7)
                self._draw_entity(painter, clone)
                painter.setOpacity(1.0)
                painter.setPen(QColor("#E55A28"))
                painter.setFont(QFont("Segoe UI", 8))
                cs = self.world_to_screen(*cur)
                painter.drawText(QPointF(cs.x() + 6, cs.y() - 6), f"{abs(dist):.2f} mm")

        elif t == TOOL_FILLET and self._mod_step == 1 \
                and self._mod_entity is not None:
            # Highlight first selected entity
            sel_pen = QPen(QColor("#E55A28"), 2.5)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.NoBrush)
            if isinstance(self._mod_entity, LineEntity):
                painter.drawLine(
                    self.world_to_screen(*self._mod_entity.start),
                    self.world_to_screen(*self._mod_entity.end))

        elif t == TOOL_CHAMFER and self._mod_step == 1 \
                and self._mod_entity is not None:
            sel_pen = QPen(QColor("#E55A28"), 2.5)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            if isinstance(self._mod_entity, LineEntity):
                painter.drawLine(
                    self.world_to_screen(*self._mod_entity.start),
                    self.world_to_screen(*self._mod_entity.end))

        # ── Dimension tools ───────────────────────────────
        elif t == TOOL_DIM_LINEAR:
            if self._dim_step == 1 and self._dim_p1 is not None:
                painter.drawLine(self.world_to_screen(*self._dim_p1),
                                 self.world_to_screen(*cur))
            elif self._dim_step == 2 and self._dim_p1 is not None \
                    and self._dim_p2 is not None:
                off_w = self._dim_offset_from_cursor(self._dim_p1, self._dim_p2, cur)
                dummy = DimLinearEntity(self._dim_p1, self._dim_p2, off_w)
                self._draw_dim_linear(painter, dummy)

        elif t == TOOL_DIM_RADIAL and self._dim_step == 1 \
                and self._dim_p1 is not None and self._mod_entity is not None:
            e = self._mod_entity
            if isinstance(e, (CircleEntity, ArcEntity)):
                ang = math.degrees(math.atan2(
                    float(cur[1] - e.center[1]), float(cur[0] - e.center[0])))
                dummy = DimRadialEntity(e.center, e.radius, ang)
                self._draw_dim_radial(painter, dummy)

    def _draw_pts_path(self, painter: QPainter, pts, closed=False):
        if len(pts) < 2:
            return
        path = QPainterPath()
        path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
        for p in pts[1:]:
            path.lineTo(self.world_to_screen(p[0], p[1]))
        if closed:
            path.closeSubpath()
        painter.drawPath(path)

    def _draw_snap_indicator(self, painter: QPainter, point: np.ndarray):
        sp  = self.world_to_screen(point[0], point[1])
        pen = QPen(QColor("#E55A28"), 2.0); pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(sp, 6.0, 6.0)

    def _draw_rubber_band(self, painter: QPainter):
        pen = QPen(QColor("#E55A28"), 1.5, Qt.DashLine); pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(229, 90, 40, 25)))
        p1, p2 = self._rubber_start_px, self._rubber_end_px
        x = min(p1.x(), p2.x()); y = min(p1.y(), p2.y())
        painter.drawRect(x, y, abs(p2.x()-p1.x()), abs(p2.y()-p1.y()))

    # ── Mouse events ──────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        pos     = event.position()
        world   = self.screen_to_world(pos.x(), pos.y())
        snapped = self._snap_result.point if self._snap_result else world

        if event.button() == Qt.MiddleButton:
            self._start_pan(pos.toPoint()); return
        if event.button() == Qt.LeftButton and self._space_held:
            self._start_pan(pos.toPoint()); return
        if event.button() == Qt.RightButton:
            self._on_right_click(); return
        if event.button() == Qt.LeftButton:
            self._handle_left_click(snapped, world, pos.toPoint(), event.modifiers())

    def mouseMoveEvent(self, event: QMouseEvent):
        pos   = event.position()
        world = self.screen_to_world(pos.x(), pos.y())
        self._cursor_world = world
        self._snap_result  = self.snap_engine.snap(
            world, self.document.visible_entities(), self._scale)
        self.cursor_moved.emit(float(self._snap_result.point[0]),
                               float(self._snap_result.point[1]))

        if self._panning and self._pan_start_px and self._pan_start_offset:
            dx = pos.x() - self._pan_start_px.x()
            dy = pos.y() - self._pan_start_px.y()
            self._pan_offset = QPointF(self._pan_start_offset.x() + dx,
                                       self._pan_start_offset.y() + dy)
            self.update(); return

        if self._dragging_image is not None:
            new_pos = world - self._drag_img_offset
            self._dragging_image.world_x = float(new_pos[0])
            self._dragging_image.world_y = float(new_pos[1])
            self.update(); return

        if self._rubber_start_px and self._tool == TOOL_SELECT:
            self._rubber_end_px = pos.toPoint()

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._panning = False; return
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CrossCursor if self._tool != TOOL_SELECT else Qt.ArrowCursor)
            return
        if self._dragging_image is not None:
            self._dragging_image = None
            self.update(); return
        if event.button() == Qt.LeftButton and self._tool == TOOL_SELECT:
            if self._rubber_start_px and self._rubber_end_px:
                self._finish_rubber_band_select(event.modifiers())
            self._rubber_start_px = None
            self._rubber_end_px   = None
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self._tool == TOOL_POLYLINE and len(self._tool_points) >= 2:
                self._finish_polyline()
            elif self._tool == TOOL_SPLINE and len(self._tool_points) >= 2:
                self._finish_spline()

    def wheelEvent(self, event: QWheelEvent):
        pos    = event.position()
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        old_w  = self.screen_to_world(pos.x(), pos.y())
        self._scale = max(0.1, min(200.0, self._scale * factor))
        new_s  = self.world_to_screen(*old_w)
        self._pan_offset += QPointF(pos.x() - new_s.x(), pos.y() - new_s.y())
        self.zoom_changed.emit(self._scale)
        self.update()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k == Qt.Key_Escape:
            self._cancel_tool()
            self.set_tool(TOOL_SELECT)
        elif k == Qt.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.OpenHandCursor)
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            # Enter/Return finishes polyline or spline in progress
            if self._tool == TOOL_POLYLINE and len(self._tool_points) >= 2:
                self._finish_polyline()
            elif self._tool == TOOL_SPLINE and len(self._tool_points) >= 2:
                self._finish_spline()

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.setCursor(
                    Qt.ArrowCursor if self._tool == TOOL_SELECT else Qt.CrossCursor)

    # ── Right-click cancel / finish ───────────────────────────

    def _on_right_click(self):
        """
        Right-click behaviour:
          • Polyline / Spline with ≥ 2 points  → commit (finish)
          • Any other in-progress multi-step tool → cancel back to step 0
          • Tool in idle state                   → return to Select
        """
        if self._tool == TOOL_POLYLINE and len(self._tool_points) >= 2:
            self._finish_polyline()
            self.status_hint.emit(self._TOOL_HINTS.get(TOOL_POLYLINE, ""))
        elif self._tool == TOOL_SPLINE and len(self._tool_points) >= 2:
            self._finish_spline()
            self.status_hint.emit(self._TOOL_HINTS.get(TOOL_SPLINE, ""))
        elif self._tool_points or self._arc_step or self._groove_step \
                or self._mod_step or self._dim_step:
            # In-progress op → cancel to start of same tool
            self._cancel_tool()
            self.status_hint.emit(self._TOOL_HINTS.get(self._tool, ""))
        else:
            # Idle → return to Select
            self.set_tool(TOOL_SELECT)
        self.update()

    # ── Tool click dispatch ───────────────────────────────────

    def _handle_left_click(self, snapped: np.ndarray, raw_world: np.ndarray,
                            screen_pos: QPoint, modifiers):
        t = self._tool

        if t == TOOL_SELECT:
            self._handle_select_click(snapped, raw_world, screen_pos, modifiers)

        # ── Drawing ───────────────────────────────────────
        elif t == TOOL_POINT:
            self._commit(PointEntity(snapped.copy()))
            self.status_hint.emit("Point placed · click to place another")

        elif t == TOOL_LINE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
                self.status_hint.emit("Line ▶ click end point  (Right-click to cancel)")
            else:
                self._commit(LineEntity(self._tool_points[0], snapped))
                self._tool_points = []
                self.status_hint.emit("Line ▶ click start point")

        elif t == TOOL_POLYLINE:
            self._tool_points.append(snapped.copy())
            n = len(self._tool_points)
            if n == 1:
                self.status_hint.emit(
                    "Polyline ▶ click next point  (Right-click / Enter to finish)")
            else:
                self.status_hint.emit(
                    f"Polyline ▶ {n} pts · click next  (Right-click / Enter to finish)")

        elif t == TOOL_RECTANGLE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
                self.status_hint.emit("Rectangle ▶ click opposite corner")
            else:
                self._commit(RectangleEntity(self._tool_points[0], snapped))
                self._tool_points = []
                self.status_hint.emit("Rectangle ▶ click first corner")

        elif t == TOOL_ELLIPSE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
                self.status_hint.emit("Ellipse ▶ click opposite corner of bounding box")
            else:
                c1 = self._tool_points[0]
                center = (c1 + snapped) / 2
                rx = abs(snapped[0] - c1[0]) / 2
                ry = abs(snapped[1] - c1[1]) / 2
                if rx > 1e-6 and ry > 1e-6:
                    self._commit(EllipseEntity(center, rx, ry))
                self._tool_points = []
                self.status_hint.emit("Ellipse ▶ click first corner of bounding box")

        elif t == TOOL_CIRCLE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
                self.status_hint.emit("Circle ▶ click to set radius")
            else:
                r = float(np.linalg.norm(snapped - self._tool_points[0]))
                if r > 1e-6:
                    self._commit(CircleEntity(self._tool_points[0], r))
                self._tool_points = []
                self.status_hint.emit("Circle ▶ click centre")

        elif t == TOOL_ARC:
            self._handle_arc_click(snapped)

        elif t == TOOL_SPLINE:
            self._tool_points.append(snapped.copy())
            n = len(self._tool_points)
            if n == 1:
                self.status_hint.emit(
                    "Spline ▶ click next control point  (Right-click / Enter to finish)")
            else:
                self.status_hint.emit(
                    f"Spline ▶ {n} pts · click next  (Right-click / Enter to finish)")

        elif t == TOOL_POLYGON:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
                self.status_hint.emit("Polygon ▶ click to set circumradius")
            else:
                center = self._tool_points[0]
                r = float(np.linalg.norm(snapped - center))
                if r > 1e-6:
                    rot = math.degrees(math.atan2(float(snapped[1]-center[1]),
                                                  float(snapped[0]-center[0])))
                    self._commit(PolygonEntity(center, self._polygon_sides, r, rot))
                self._tool_points = []
                self.status_hint.emit("Polygon ▶ click centre")

        elif t == TOOL_SEMICIRCLE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
                self.status_hint.emit("Semi-circle ▶ click to set radius")
            else:
                center = self._tool_points[0]
                r = float(np.linalg.norm(snapped - center))
                if r > 1e-6:
                    bump = math.degrees(math.atan2(float(snapped[1]-center[1]),
                                                   float(snapped[0]-center[0])))
                    self._commit(SemiCircleEntity(center, r, (bump - 90) % 360))
                self._tool_points = []
                self.status_hint.emit("Semi-circle ▶ click centre")

        elif t == TOOL_GROOVE:
            self._handle_groove_click(snapped)

        elif t == TOOL_TEXT:
            self._handle_text_click(snapped)

        # ── Modify ────────────────────────────────────────
        elif t in (TOOL_MOVE, TOOL_COPY_TOOL):
            prev_step = self._mod_step
            self._handle_move_click(snapped)
            if prev_step == 0 and self._mod_step == 1:
                verb = "Copy" if t == TOOL_COPY_TOOL else "Move"
                self.status_hint.emit(f"{verb} ▶ click destination point")
            elif self._mod_step == 0:
                verb = "Copy" if t == TOOL_COPY_TOOL else "Move"
                self.status_hint.emit(
                    f"{verb} ▶ click base point  (select entities first)")

        elif t == TOOL_ROTATE:
            prev_step = self._mod_step
            self._handle_rotate_click(snapped, raw_world)
            if prev_step == 0 and self._mod_step == 1:
                self.status_hint.emit("Rotate ▶ click to set angle")
            else:
                self.status_hint.emit(
                    "Rotate ▶ click pivot  (select entities first)")

        elif t == TOOL_MIRROR:
            prev_step = self._mod_step
            self._handle_mirror_click(snapped)
            if prev_step == 0 and self._mod_step == 1:
                self.status_hint.emit("Mirror ▶ click second axis point")
            else:
                self.status_hint.emit(
                    "Mirror ▶ click axis start  (select entities first)")

        elif t == TOOL_OFFSET:
            prev_step = self._mod_step
            self._handle_offset_click(snapped, raw_world)
            if prev_step == 0 and self._mod_step == 1:
                self.status_hint.emit("Offset ▶ click side to offset towards")
            else:
                self.status_hint.emit("Offset ▶ click entity to offset")

        elif t == TOOL_TRIM:
            self._handle_trim_click(snapped)
            self.status_hint.emit("Trim ▶ click segment to remove")

        elif t == TOOL_EXTEND:
            prev_step = self._mod_step
            self._handle_extend_click(snapped)
            if prev_step == 0 and self._mod_step == 1:
                self.status_hint.emit("Extend ▶ click target boundary")
            else:
                self.status_hint.emit("Extend ▶ click line to extend")

        elif t == TOOL_FILLET:
            prev_step = self._mod_step
            self._handle_fillet_click(snapped)
            if prev_step == 0 and self._mod_step == 1:
                self.status_hint.emit(
                    "Fillet ▶ click second line  (radius prompt will follow)")
            else:
                self.status_hint.emit("Fillet ▶ click first line")

        elif t == TOOL_CHAMFER:
            prev_step = self._mod_step
            self._handle_chamfer_click(snapped)
            if prev_step == 0 and self._mod_step == 1:
                self.status_hint.emit(
                    "Chamfer ▶ click second line  (distances prompt will follow)")
            else:
                self.status_hint.emit("Chamfer ▶ click first line")

        elif t == TOOL_BREAK:
            self._handle_break_click(snapped)
            self.status_hint.emit("Break ▶ click entity at break point")

        # ── Annotation ────────────────────────────────────
        elif t == TOOL_DIM_LINEAR:
            prev_step = self._dim_step
            self._handle_dim_linear_click(snapped)
            if prev_step == 0:
                self.status_hint.emit("Linear Dim ▶ click second point")
            elif prev_step == 1:
                self.status_hint.emit(
                    "Linear Dim ▶ click offset position for dimension line")
            else:
                self.status_hint.emit("Linear Dim ▶ click first point")

        elif t == TOOL_DIM_RADIAL:
            prev_step = self._dim_step
            self._handle_dim_radial_click(snapped)
            if prev_step == 0 and self._dim_step == 1:
                self.status_hint.emit(
                    "Radial Dim ▶ click to set leader angle")
            else:
                self.status_hint.emit("Radial Dim ▶ click a circle or arc")

        self.update()

    # ── Select ────────────────────────────────────────────────

    def _handle_select_click(self, snapped, raw_world, screen_pos, modifiers):
        img_hit = self._hit_test_image(raw_world)
        if img_hit and not img_hit.locked:
            for i in self._images: i.selected = False
            img_hit.selected = True
            self._dragging_image  = img_hit
            self._drag_img_offset = raw_world - np.array([img_hit.world_x, img_hit.world_y])
            self.document.deselect_all()
            self.selection_changed.emit([])
            self.update(); return

        for i in self._images: i.selected = False

        hit = self._hit_test(snapped)
        if hit:
            if not (modifiers & Qt.ShiftModifier):
                self.document.deselect_all()
            hit.selected = not hit.selected
            self.selection_changed.emit(self.document.selected_entities())
        else:
            if not (modifiers & Qt.ShiftModifier):
                self.document.deselect_all()
                self.selection_changed.emit([])
            self._rubber_start_px = screen_pos
            self._rubber_end_px   = screen_pos
        self.update()

    # ── Arc ───────────────────────────────────────────────────

    def _handle_arc_click(self, snapped):
        if self._arc_step == 0:
            self._arc_center = snapped.copy(); self._arc_step = 1
            self.status_hint.emit("Arc ▶ click to set radius & start angle")
        elif self._arc_step == 1:
            self._arc_radius = float(np.linalg.norm(snapped - self._arc_center))
            self._arc_start_angle = math.degrees(
                math.atan2(float(snapped[1]-self._arc_center[1]),
                           float(snapped[0]-self._arc_center[0]))) % 360
            self._arc_step = 2
            self.status_hint.emit("Arc ▶ click to set end angle")
        elif self._arc_step == 2:
            ea = math.degrees(math.atan2(float(snapped[1]-self._arc_center[1]),
                                         float(snapped[0]-self._arc_center[0]))) % 360
            if self._arc_radius > 1e-6:
                self._commit(ArcEntity(self._arc_center, self._arc_radius,
                                       self._arc_start_angle, ea))
            self._arc_step = 0; self._arc_center = None
            self.status_hint.emit("Arc ▶ click centre")

    # ── Groove ────────────────────────────────────────────────

    def _handle_groove_click(self, snapped):
        if self._groove_step == 0:
            self._groove_c1 = snapped.copy(); self._groove_step = 1
            self.status_hint.emit("Groove ▶ click second centre")
        elif self._groove_step == 1:
            self._groove_c2 = snapped.copy(); self._groove_step = 2
            self.status_hint.emit("Groove ▶ click to set width (drag perpendicular)")
        elif self._groove_step == 2:
            c1, c2 = self._groove_c1, self._groove_c2
            axis = c2 - c1
            aln  = float(np.linalg.norm(axis))
            if aln > 1e-6:
                perp = np.array([-axis[1], axis[0]]) / aln
                r    = max(abs(float(np.dot(snapped - (c1+c2)/2, perp))), 0.5)
                self._commit(GrooveEntity(c1, c2, r))
            self._groove_step = 0; self._groove_c1 = self._groove_c2 = None
            self.status_hint.emit("Groove ▶ click first centre")

    # ── Text ──────────────────────────────────────────────────

    def _handle_text_click(self, snapped):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDoubleSpinBox, QPushButton, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Insert Text")
        dlg.setModal(True)
        dlg.setStyleSheet("QDialog{background:#F8F9FA;} QLabel{color:#1A1A24;font-size:13px;}")
        form = QFormLayout(dlg)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(8)
        txt_edit = QLineEdit()
        txt_edit.setStyleSheet("background:#FFFFFF;border:1px solid #E0E0E0;border-radius:3px;padding:4px 8px;font-size:13px;")
        h_spin = QDoubleSpinBox()
        h_spin.setRange(0.1, 1000); h_spin.setValue(5.0); h_spin.setSuffix(" mm")
        h_spin.setStyleSheet("background:#FFFFFF;border:1px solid #E0E0E0;border-radius:3px;padding:4px 8px;font-size:13px;")
        form.addRow("Text:", txt_edit)
        form.addRow("Height:", h_spin)
        row = QHBoxLayout(); row.addStretch()
        ok = QPushButton("Add"); ok.setDefault(True)
        ok.setStyleSheet("QPushButton{background:#E55A28;color:#FFFFFF;border:none;border-radius:4px;padding:5px 16px;font-size:13px;font-weight:600;} QPushButton:hover{background:#CC4D22;}")
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet("QPushButton{background:#FFF;color:#1A1A24;border:1px solid #E0E0E0;border-radius:4px;padding:5px 14px;font-size:13px;} QPushButton:hover{background:#F0F2F5;}")
        cancel.clicked.connect(dlg.reject)
        row.addWidget(cancel); row.addWidget(ok)
        form.addRow(row)
        txt_edit.setFocus()
        if dlg.exec() == QDialog.Accepted and txt_edit.text().strip():
            self._commit(TextEntity(snapped.copy(), txt_edit.text().strip(),
                                    h_spin.value()))

    # ── Move / Copy ───────────────────────────────────────────

    def _handle_move_click(self, snapped):
        is_copy = self._tool == TOOL_COPY_TOOL
        if self._mod_step == 0:
            if not self.document.selected_entities():
                hit = self._hit_test(snapped)
                if hit:
                    self.document.deselect_all()
                    hit.selected = True
                    self.selection_changed.emit([hit])
            if self.document.selected_entities():
                self._mod_base = snapped.copy()
                self._mod_step = 1
        else:
            delta = snapped - self._mod_base
            snap  = self.document.begin_operation()
            if is_copy:
                new_ents = []
                for e in self.document.selected_entities():
                    clone = e.clone()
                    clone.translate(float(delta[0]), float(delta[1]))
                    clone.selected = False
                    new_ents.append(clone)
                for ne in new_ents:
                    self.document.entities.append(ne)
            else:
                for e in self.document.selected_entities():
                    e.translate(float(delta[0]), float(delta[1]))
            self.document.commit_operation(snap)
            self._mod_step = 0; self._mod_base = None
            self.selection_changed.emit(self.document.selected_entities())
            self.entity_added.emit(None)

    # ── Rotate ────────────────────────────────────────────────

    def _handle_rotate_click(self, snapped, raw_world):
        if self._mod_step == 0:
            self._mod_base = snapped.copy()
            self._mod_ref_angle = math.degrees(
                math.atan2(float(raw_world[1] - snapped[1]),
                           float(raw_world[0] - snapped[0])))
            self._mod_step = 1
        else:
            pivot = self._mod_base
            cur_ang = math.degrees(math.atan2(float(snapped[1] - pivot[1]),
                                              float(snapped[0] - pivot[0])))
            rotation = cur_ang - self._mod_ref_angle
            snap = self.document.begin_operation()
            for e in self.document.selected_entities():
                e.rotate(rotation, pivot)
            self.document.commit_operation(snap)
            self._mod_step = 0; self._mod_base = None
            self.selection_changed.emit(self.document.selected_entities())
            self.entity_added.emit(None)

    # ── Mirror ────────────────────────────────────────────────

    def _handle_mirror_click(self, snapped):
        if self._mod_step == 0:
            self._mod_base = snapped.copy()
            self._mod_step = 1
        else:
            axis_p1 = self._mod_base
            axis_p2 = snapped
            if float(np.linalg.norm(axis_p2 - axis_p1)) < 1e-6:
                return
            snap = self.document.begin_operation()
            for e in self.document.selected_entities():
                self._mirror_entity(e, axis_p1, axis_p2)
            self.document.commit_operation(snap)
            self._mod_step = 0; self._mod_base = None
            self.selection_changed.emit(self.document.selected_entities())
            self.entity_added.emit(None)

    def _mirror_entity(self, e: Entity, p1: np.ndarray, p2: np.ndarray):
        """Reflect entity across axis p1→p2 in-place."""
        if isinstance(e, LineEntity):
            e.start = mirror_point(e.start, p1, p2)
            e.end   = mirror_point(e.end,   p1, p2)
        elif isinstance(e, PolylineEntity):
            e.points = [mirror_point(p, p1, p2) for p in e.points]
        elif isinstance(e, RectangleEntity):
            e.corner1 = mirror_point(e.corner1, p1, p2)
            e.corner2 = mirror_point(e.corner2, p1, p2)
        elif isinstance(e, CircleEntity):
            e.center = mirror_point(e.center, p1, p2)
        elif isinstance(e, ArcEntity):
            e.center      = mirror_point(e.center, p1, p2)
            # Mirror angles
            axis_ang = math.degrees(math.atan2(float(p2[1]-p1[1]), float(p2[0]-p1[0])))
            sa = (2 * axis_ang - e.start_angle) % 360
            ea = (2 * axis_ang - e.end_angle) % 360
            e.start_angle, e.end_angle = ea, sa   # swap to keep CCW
        elif isinstance(e, SplineEntity):
            e.control_points = [mirror_point(p, p1, p2) for p in e.control_points]
        elif isinstance(e, PolygonEntity):
            e.center = mirror_point(e.center, p1, p2)
        elif isinstance(e, EllipseEntity):
            e.center = mirror_point(e.center, p1, p2)
        elif isinstance(e, SemiCircleEntity):
            e.center    = mirror_point(e.center, p1, p2)
            axis_ang    = math.degrees(math.atan2(float(p2[1]-p1[1]), float(p2[0]-p1[0])))
            e.flat_angle = (2 * axis_ang - e.flat_angle) % 360
        elif isinstance(e, GrooveEntity):
            e.center1 = mirror_point(e.center1, p1, p2)
            e.center2 = mirror_point(e.center2, p1, p2)
        elif isinstance(e, PointEntity):
            e.position = mirror_point(e.position, p1, p2)
        elif isinstance(e, TextEntity):
            e.position = mirror_point(e.position, p1, p2)

    # ── Offset ────────────────────────────────────────────────

    def _handle_offset_click(self, snapped, raw_world):
        if self._mod_step == 0:
            hit = self._hit_test(raw_world)
            if hit and isinstance(hit, (LineEntity, PolylineEntity,
                                        CircleEntity, ArcEntity)):
                self.document.deselect_all()
                hit.selected = True
                self._mod_entity = hit
                self._mod_step   = 1
        else:
            e    = self._mod_entity
            dist = self._offset_distance(e, snapped)
            clone = self._compute_offset(e, dist)
            if clone is not None:
                snap = self.document.begin_operation()
                self.document.add_entity(clone, push_undo=False)
                self.document.commit_operation(snap)
                self.entity_added.emit(clone)
            self._mod_step = 0; self._mod_entity = None
            self.document.deselect_all()
            self.selection_changed.emit([])

    def _offset_distance(self, e: Entity, cursor: np.ndarray) -> float:
        """Signed offset distance from cursor to entity (positive = left)."""
        if isinstance(e, LineEntity):
            d = e.end - e.start
            perp = np.array([-d[1], d[0]])
            l = float(np.linalg.norm(perp))
            if l < 1e-10:
                return 0.0
            perp /= l
            mid = (e.start + e.end) / 2
            raw = float(np.dot(cursor - mid, perp))
            dist = float(np.linalg.norm(cursor - e.nearest_point(cursor)))
            return dist if raw > 0 else -dist
        elif isinstance(e, PolylineEntity) and len(e.points) >= 2:
            mid = e.points[len(e.points)//2]
            d   = e.points[len(e.points)//2] - e.points[len(e.points)//2 - 1]
            perp = np.array([-d[1], d[0]])
            l = float(np.linalg.norm(perp))
            if l < 1e-10:
                return float(np.linalg.norm(cursor - mid))
            perp /= l
            raw  = float(np.dot(cursor - mid, perp))
            dist = float(np.linalg.norm(cursor - e.nearest_point(cursor)))
            return dist if raw > 0 else -dist
        elif isinstance(e, CircleEntity):
            d = float(np.linalg.norm(cursor - e.center))
            return d - e.radius
        elif isinstance(e, ArcEntity):
            d = float(np.linalg.norm(cursor - e.center))
            return d - e.radius
        return 0.0

    def _compute_offset(self, e: Entity, dist: float) -> Optional[Entity]:
        if abs(dist) < 1e-6:
            return None
        if isinstance(e, LineEntity):
            p1, p2 = offset_segment(e.start, e.end, dist)
            ne = LineEntity(p1, p2)
        elif isinstance(e, PolylineEntity):
            pts = offset_polyline(e.points, dist, e.closed)
            if len(pts) < 2:
                return None
            ne = PolylineEntity([np.array(p) for p in pts], e.closed)
        elif isinstance(e, CircleEntity):
            new_r = e.radius + dist
            if new_r < 1e-6:
                return None
            ne = CircleEntity(e.center.copy(), new_r)
        elif isinstance(e, ArcEntity):
            new_r = e.radius + dist
            if new_r < 1e-6:
                return None
            ne = ArcEntity(e.center.copy(), new_r, e.start_angle, e.end_angle)
        else:
            return None
        ne.layer = e.layer
        ne.color = e.color
        return ne

    # ── Trim ──────────────────────────────────────────────────

    def _handle_trim_click(self, snapped):
        hit = self._hit_test(snapped)
        if hit is None or not isinstance(hit, LineEntity):
            return
        ts = t_values_on_line(hit.start, hit.end,
                              self.document.visible_entities(), hit.id)
        if not ts:
            return
        # Find t of click
        d   = hit.end - hit.start
        dl2 = float(np.dot(d, d))
        if dl2 < 1e-12:
            return
        t_click = float(np.dot(snapped - hit.start, d)) / dl2

        all_t = sorted(set([0.0] + ts + [1.0]))
        snap = self.document.begin_operation()
        self.document.entities = [e for e in self.document.entities if e.id != hit.id]
        for i in range(len(all_t) - 1):
            t0, t1 = all_t[i], all_t[i + 1]
            if t0 <= t_click <= t1:
                continue    # this segment is trimmed away
            if t1 - t0 < 1e-9:
                continue
            p0 = hit.start + t0 * d
            p1 = hit.start + t1 * d
            ne = LineEntity(p0, p1)
            ne.layer = hit.layer; ne.color = hit.color
            self.document.entities.append(ne)
        self.document.commit_operation(snap)
        self.document.deselect_all()
        self.selection_changed.emit([])
        self.entity_added.emit(None)

    # ── Extend ────────────────────────────────────────────────

    def _handle_extend_click(self, snapped):
        if self._mod_step == 0:
            # Click near endpoint of entity to extend
            hit = self._hit_test(snapped)
            if hit and isinstance(hit, LineEntity):
                self._mod_entity = hit
                self._mod_step   = 1
        else:
            target = self._hit_test(snapped)
            src    = self._mod_entity
            if target and isinstance(src, LineEntity):
                self._do_extend(src, snapped, target)
            self._mod_step = 0; self._mod_entity = None

    def _do_extend(self, src: LineEntity, click_pt: np.ndarray, target: Entity):
        """Extend src to first intersection with target."""
        intersections = []
        if isinstance(target, LineEntity):
            res = line_line_intersect(src.start, src.end, target.start, target.end)
            if res:
                t, u, pt = res
                if 0.0 <= u <= 1.0:
                    intersections.append((t, pt))
        elif isinstance(target, CircleEntity):
            for t, pt in circle_line_t(target.center, target.radius, src.start, src.end):
                intersections.append((t, pt))

        if not intersections:
            return

        # Determine which end is closer to click
        d    = src.end - src.start
        dl2  = float(np.dot(d, d))
        t_click = float(np.dot(click_pt - src.start, d)) / max(dl2, 1e-12)

        if t_click > 0.5:
            # Extend end
            best = max(intersections, key=lambda x: x[0])
        else:
            # Extend start
            best = min(intersections, key=lambda x: x[0])

        t_val, new_pt = best
        snap = self.document.begin_operation()
        if t_click > 0.5:
            src.end = new_pt
        else:
            src.start = new_pt
        self.document.commit_operation(snap)
        self.selection_changed.emit(self.document.selected_entities())
        self.entity_added.emit(None)

    # ── Fillet ────────────────────────────────────────────────

    def _handle_fillet_click(self, snapped):
        if self._mod_step == 0:
            hit = self._hit_test(snapped)
            if hit and isinstance(hit, LineEntity):
                self._mod_entity = hit
                self._mod_step   = 1
        else:
            hit2 = self._hit_test(snapped)
            src  = self._mod_entity
            if hit2 and isinstance(src, LineEntity) and isinstance(hit2, LineEntity) \
                    and hit2 is not src:
                self._do_fillet(src, hit2)
            self._mod_step = 0; self._mod_entity = None

    def _do_fillet(self, e1: LineEntity, e2: LineEntity):
        radius, ok = QInputDialog.getDouble(
            self, "Fillet Radius", "Radius (mm):", 5.0, 0.01, 10000.0, 2)
        if not ok or radius < 1e-6:
            return
        result = fillet_lines(e1.start, e1.end, e2.start, e2.end, radius)
        if result is None:
            return
        tp1, tp2, arc_center, arc_sa, arc_ea, corner = result
        snap = self.document.begin_operation()
        # Trim line 1 to tp1
        e1.end = tp1
        # Trim line 2 start to tp2
        e2.start = tp2
        # Add fillet arc
        arc = ArcEntity(arc_center, radius, arc_sa, arc_ea)
        arc.layer = e1.layer; arc.color = e1.color
        self.document.add_entity(arc, push_undo=False)
        self.document.commit_operation(snap)
        self.entity_added.emit(arc)

    # ── Chamfer ───────────────────────────────────────────────

    def _handle_chamfer_click(self, snapped):
        if self._mod_step == 0:
            hit = self._hit_test(snapped)
            if hit and isinstance(hit, LineEntity):
                self._mod_entity = hit
                self._mod_step   = 1
        else:
            hit2 = self._hit_test(snapped)
            src  = self._mod_entity
            if hit2 and isinstance(src, LineEntity) and isinstance(hit2, LineEntity) \
                    and hit2 is not src:
                self._do_chamfer(src, hit2)
            self._mod_step = 0; self._mod_entity = None

    def _do_chamfer(self, e1: LineEntity, e2: LineEntity):
        d1, ok1 = QInputDialog.getDouble(
            self, "Chamfer", "Distance 1 (mm):", 5.0, 0.01, 10000.0, 2)
        if not ok1:
            return
        d2, ok2 = QInputDialog.getDouble(
            self, "Chamfer", "Distance 2 (mm):", d1, 0.01, 10000.0, 2)
        if not ok2:
            return
        result = chamfer_lines(e1.start, e1.end, e2.start, e2.end, d1, d2)
        if result is None:
            return
        tp1, tp2, corner = result
        snap = self.document.begin_operation()
        e1.end   = tp1
        e2.start = tp2
        chamfer_line = LineEntity(tp1, tp2)
        chamfer_line.layer = e1.layer; chamfer_line.color = e1.color
        self.document.add_entity(chamfer_line, push_undo=False)
        self.document.commit_operation(snap)
        self.entity_added.emit(chamfer_line)

    # ── Break ─────────────────────────────────────────────────

    def _handle_break_click(self, snapped):
        hit = self._hit_test(snapped)
        if hit is None:
            return
        snap = self.document.begin_operation()
        if isinstance(hit, LineEntity):
            d   = hit.end - hit.start
            dl2 = float(np.dot(d, d))
            if dl2 < 1e-12:
                return
            t = max(0.001, min(0.999,
                    float(np.dot(snapped - hit.start, d)) / dl2))
            mid = hit.start + t * d
            # Replace with two lines
            self.document.entities = [e for e in self.document.entities
                                       if e.id != hit.id]
            for p1, p2 in [(hit.start, mid), (mid, hit.end)]:
                ne = LineEntity(p1, p2)
                ne.layer = hit.layer; ne.color = hit.color
                self.document.entities.append(ne)
        elif isinstance(hit, PolylineEntity) and len(hit.points) >= 2:
            # Find nearest segment
            best_i = 0; best_dist = float("inf")
            for i in range(len(hit.points) - 1):
                seg_d = hit.points[i+1] - hit.points[i]
                lsq   = float(np.dot(seg_d, seg_d))
                if lsq < 1e-12:
                    continue
                tt = max(0.0, min(1.0, float(np.dot(snapped - hit.points[i], seg_d)) / lsq))
                near = hit.points[i] + tt * seg_d
                dist = float(np.linalg.norm(snapped - near))
                if dist < best_dist:
                    best_dist = dist; best_i = i
            mid = hit.points[best_i] + 0.5 * (hit.points[best_i+1] - hit.points[best_i])
            pts1 = hit.points[:best_i+1] + [mid]
            pts2 = [mid] + hit.points[best_i+1:]
            self.document.entities = [e for e in self.document.entities if e.id != hit.id]
            for pts in [pts1, pts2]:
                if len(pts) >= 2:
                    ne = PolylineEntity(pts)
                    ne.layer = hit.layer; ne.color = hit.color
                    self.document.entities.append(ne)
        self.document.commit_operation(snap)
        self.document.deselect_all()
        self.selection_changed.emit([])
        self.entity_added.emit(None)

    # ── Linear Dimension ──────────────────────────────────────

    def _handle_dim_linear_click(self, snapped):
        if self._dim_step == 0:
            self._dim_p1  = snapped.copy()
            self._dim_step = 1
        elif self._dim_step == 1:
            self._dim_p2  = snapped.copy()
            self._dim_step = 2
        else:
            off_w = self._dim_offset_from_cursor(self._dim_p1, self._dim_p2, snapped)
            self._commit(DimLinearEntity(self._dim_p1, self._dim_p2, off_w))
            self._dim_step = 0; self._dim_p1 = self._dim_p2 = None

    def _dim_offset_from_cursor(self, p1: np.ndarray, p2: np.ndarray,
                                  cursor: np.ndarray) -> float:
        """Signed distance from the p1-p2 line to cursor (used as dim offset)."""
        d = p2 - p1
        l = float(np.linalg.norm(d))
        if l < 1e-10:
            return 10.0
        perp = np.array([-d[1], d[0]]) / l
        return float(np.dot(cursor - p1, perp))

    # ── Radial Dimension ──────────────────────────────────────

    def _handle_dim_radial_click(self, snapped):
        if self._dim_step == 0:
            hit = self._hit_test(snapped)
            if hit and isinstance(hit, (CircleEntity, ArcEntity)):
                self._mod_entity = hit
                self._dim_p1     = snapped.copy()
                self._dim_step   = 1
        else:
            e = self._mod_entity
            if e and isinstance(e, (CircleEntity, ArcEntity)):
                ang = math.degrees(math.atan2(
                    float(snapped[1] - e.center[1]),
                    float(snapped[0] - e.center[0])))
                is_dia = isinstance(e, CircleEntity)
                self._commit(DimRadialEntity(e.center, e.radius, ang, is_dia))
            self._dim_step = 0; self._dim_p1 = None; self._mod_entity = None

    # ── Finish polyline / spline ──────────────────────────────

    def _finish_polyline(self):
        if len(self._tool_points) >= 2:
            self._commit(PolylineEntity(self._tool_points))
        self._tool_points = []; self.update()

    def _finish_spline(self):
        if len(self._tool_points) >= 2:
            self._commit(SplineEntity(self._tool_points))
        self._tool_points = []; self.update()

    # ── Rubber-band select ────────────────────────────────────

    def _finish_rubber_band_select(self, modifiers):
        p1, p2 = self._rubber_start_px, self._rubber_end_px
        rect   = QRect(min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                       abs(p2.x()-p1.x()), abs(p2.y()-p1.y()))
        if not (modifiers & Qt.ShiftModifier):
            self.document.deselect_all()
        for entity in self.document.visible_entities():
            bb  = entity.bounding_box()
            sp1 = self.world_to_screen(bb[0], bb[1])
            sp2 = self.world_to_screen(bb[2], bb[3])
            er  = QRect(int(min(sp1.x(), sp2.x())), int(min(sp1.y(), sp2.y())),
                        int(abs(sp2.x()-sp1.x())), int(abs(sp2.y()-sp1.y())))
            if rect.intersects(er):
                entity.selected = True
        self.selection_changed.emit(self.document.selected_entities())
        self.update()

    # ── Hit tests ─────────────────────────────────────────────

    def _hit_test(self, world_pt: np.ndarray,
                  threshold_px: float = 9.0) -> Optional[Entity]:
        thr  = threshold_px / self._scale
        best = None; best_dist = float("inf")
        for entity in reversed(self.document.visible_entities()):
            nearest = entity.nearest_point(world_pt)
            dist    = float(np.linalg.norm(world_pt - nearest))
            if dist < thr and dist < best_dist:
                best_dist = dist; best = entity
        return best

    def _hit_test_image(self, world_pt: np.ndarray) -> Optional[ImageOverlay]:
        for img in reversed(self._images):
            if not img.visible:
                continue
            if (img.world_x <= world_pt[0] <= img.world_x + img.world_w and
                    img.world_y - img.world_h <= world_pt[1] <= img.world_y):
                return img
        return None

    # ── Commit / Helpers ──────────────────────────────────────

    def _commit(self, entity: Entity):
        """Add entity with a single, clean undo snapshot."""
        snap = self.document.begin_operation()
        self.document.add_entity(entity, push_undo=False)   # snapshot handled by commit
        self.document.commit_operation(snap)
        self.entity_added.emit(entity)

    def _start_pan(self, screen_pos: QPoint):
        self._panning          = True
        self._pan_start_px     = screen_pos
        self._pan_start_offset = QPointF(self._pan_offset)
        self.setCursor(Qt.ClosedHandCursor)

    def _cancel_tool(self):
        self._tool_points  = []
        self._arc_step     = 0;   self._arc_center   = None
        self._groove_step  = 0;   self._groove_c1    = self._groove_c2 = None
        self._mod_step     = 0;   self._mod_base     = None; self._mod_entity = None
        self._dim_step     = 0;   self._dim_p1       = self._dim_p2 = None
        self._rubber_start_px = self._rubber_end_px = None
        self._dragging_image  = None
