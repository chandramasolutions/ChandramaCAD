from __future__ import annotations
import math
import numpy as np
from typing import Optional, Callable
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QPoint, QRect, Signal, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QCursor, QFont,
    QPainterPath, QKeyEvent, QMouseEvent, QWheelEvent,
)
from core.document import Document
from core.entities import (
    Entity, LineEntity, PolylineEntity, RectangleEntity,
    CircleEntity, ArcEntity, SplineEntity,
)
from core.snap_engine import SnapEngine, SnapResult


# Tool mode constants
TOOL_SELECT = "select"
TOOL_LINE = "line"
TOOL_POLYLINE = "polyline"
TOOL_RECTANGLE = "rectangle"
TOOL_CIRCLE = "circle"
TOOL_ARC = "arc"
TOOL_SPLINE = "spline"


class Canvas(QWidget):
    entity_added = Signal(object)
    selection_changed = Signal(list)
    cursor_moved = Signal(float, float)
    zoom_changed = Signal(float)
    tool_changed = Signal(str)

    def __init__(self, document: Document, snap_engine: SnapEngine, parent=None):
        super().__init__(parent)
        self.document = document
        self.snap_engine = snap_engine

        # View transform
        self._scale: float = 5.0  # pixels per mm (100% ≈ screen res at 96dpi)
        self._pan_offset: QPointF = QPointF(0.0, 0.0)

        # Grid
        self.grid_visible: bool = True
        self.grid_size: float = 10.0  # mm

        # Current tool
        self._tool: str = TOOL_SELECT
        self._tool_points: list[np.ndarray] = []   # accumulated input points
        self._arc_step: int = 0   # 0=center, 1=radius, 2=end angle
        self._arc_center: Optional[np.ndarray] = None
        self._arc_radius: float = 0.0
        self._arc_start_angle: float = 0.0

        # Snap
        self._snap_result: Optional[SnapResult] = None
        self._cursor_world: np.ndarray = np.zeros(2)

        # Pan state
        self._panning: bool = False
        self._pan_start_px: Optional[QPoint] = None
        self._pan_start_offset: Optional[QPointF] = None

        # Select state
        self._rubber_start_px: Optional[QPoint] = None
        self._rubber_end_px: Optional[QPoint] = None

        # Move state
        self._moving: bool = False
        self._move_start_world: Optional[np.ndarray] = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.ArrowCursor)

    # ── Public API ───────────────────────────────────────

    def set_tool(self, tool: str):
        self._cancel_tool()
        self._tool = tool
        if tool == TOOL_SELECT:
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.CrossCursor)
        self.tool_changed.emit(tool)
        self.update()

    def get_tool(self) -> str:
        return self._tool

    def set_grid_visible(self, visible: bool):
        self.grid_visible = visible
        self.update()

    def fit_to_screen(self):
        entities = self.document.visible_entities()
        if not entities:
            self._scale = 5.0
            self._pan_offset = QPointF(self.width() / 2, self.height() / 2)
            self.update()
            return
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for e in entities:
            bb = e.bounding_box()
            min_x = min(min_x, bb[0])
            min_y = min(min_y, bb[1])
            max_x = max(max_x, bb[2])
            max_y = max(max_y, bb[3])
        if max_x <= min_x:
            max_x = min_x + 10
        if max_y <= min_y:
            max_y = min_y + 10
        margin = 0.1
        w_world = (max_x - min_x) * (1 + 2 * margin)
        h_world = (max_y - min_y) * (1 + 2 * margin)
        sx = self.width() / w_world if w_world > 0 else 5.0
        sy = self.height() / h_world if h_world > 0 else 5.0
        self._scale = min(sx, sy)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        screen_cx, screen_cy = self.width() / 2, self.height() / 2
        self._pan_offset = QPointF(screen_cx - cx * self._scale,
                                   screen_cy + cy * self._scale)
        self.zoom_changed.emit(self._scale)
        self.update()

    # ── Coordinate transforms ────────────────────────────

    def world_to_screen(self, wx: float, wy: float) -> QPointF:
        sx = wx * self._scale + self._pan_offset.x()
        sy = -wy * self._scale + self._pan_offset.y()
        return QPointF(sx, sy)

    def screen_to_world(self, sx: float, sy: float) -> np.ndarray:
        wx = (sx - self._pan_offset.x()) / self._scale
        wy = -(sy - self._pan_offset.y()) / self._scale
        return np.array([wx, wy])

    # ── Paint ────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Background
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        # 1. Grid
        if self.grid_visible:
            self._draw_grid(painter)

        # 2. Entities
        for entity in self.document.visible_entities():
            self._draw_entity(painter, entity)

        # 3. Selection handles
        for entity in self.document.selected_entities():
            self._draw_selection_handles(painter, entity)

        # 4. Tool rubber-band preview
        self._draw_tool_preview(painter)

        # 5. Snap indicator
        if self._snap_result and self._snap_result.snap_type != "none":
            self._draw_snap_indicator(painter, self._snap_result.point)

        # 6. Rubber-band selection rect
        if self._rubber_start_px and self._rubber_end_px:
            self._draw_rubber_band(painter)

        painter.end()

    def _draw_grid(self, painter: QPainter):
        gs = self.grid_size
        pen_minor = QPen(QColor("#EEEEEE"), 0.5)
        pen_major = QPen(QColor("#E0E0E0"), 1.0)

        left_w = self.screen_to_world(0, 0)[0]
        right_w = self.screen_to_world(self.width(), 0)[0]
        top_w = self.screen_to_world(0, 0)[1]
        bottom_w = self.screen_to_world(0, self.height())[1]

        x_start = math.floor(left_w / gs) * gs
        x_end = math.ceil(right_w / gs) * gs
        y_start = math.floor(bottom_w / gs) * gs
        y_end = math.ceil(top_w / gs) * gs

        major_every = 10  # every 10 grid lines = major

        x = x_start
        while x <= x_end:
            is_major = abs(round(x / gs) % major_every) < 0.01
            painter.setPen(pen_major if is_major else pen_minor)
            sp_top = self.world_to_screen(x, top_w)
            sp_bot = self.world_to_screen(x, bottom_w)
            painter.drawLine(sp_top, sp_bot)
            x += gs

        y = y_start
        while y <= y_end:
            is_major = abs(round(y / gs) % major_every) < 0.01
            painter.setPen(pen_major if is_major else pen_minor)
            sp_left = self.world_to_screen(left_w, y)
            sp_right = self.world_to_screen(right_w, y)
            painter.drawLine(sp_left, sp_right)
            y += gs

        # Origin axes
        pen_axis = QPen(QColor("#CCCCCC"), 1.0, Qt.DashLine)
        painter.setPen(pen_axis)
        sp_origin_h_l = self.world_to_screen(left_w, 0)
        sp_origin_h_r = self.world_to_screen(right_w, 0)
        painter.drawLine(sp_origin_h_l, sp_origin_h_r)
        sp_origin_v_t = self.world_to_screen(0, top_w)
        sp_origin_v_b = self.world_to_screen(0, bottom_w)
        painter.drawLine(sp_origin_v_t, sp_origin_v_b)

    def _draw_entity(self, painter: QPainter, entity: Entity):
        layer = self.document.get_layer(entity.layer)
        color_str = entity.color if entity.color else (layer.color if layer else "#1A1A24")
        color = QColor(color_str)
        width = 2.0 if entity.selected else 1.0
        pen = QPen(color, width)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if isinstance(entity, LineEntity):
            p1 = self.world_to_screen(*entity.start)
            p2 = self.world_to_screen(*entity.end)
            painter.drawLine(p1, p2)

        elif isinstance(entity, (PolylineEntity, RectangleEntity, SplineEntity)):
            pts = entity.to_points()
            if len(pts) < 2:
                return
            path = QPainterPath()
            sp = self.world_to_screen(pts[0][0], pts[0][1])
            path.moveTo(sp)
            for p in pts[1:]:
                spt = self.world_to_screen(p[0], p[1])
                path.lineTo(spt)
            if isinstance(entity, (PolylineEntity, RectangleEntity)):
                closed = (isinstance(entity, RectangleEntity) or
                          (isinstance(entity, PolylineEntity) and entity.closed))
                if closed:
                    path.closeSubpath()
            painter.drawPath(path)

        elif isinstance(entity, CircleEntity):
            center = self.world_to_screen(*entity.center)
            r_px = entity.radius * self._scale
            painter.drawEllipse(center, r_px, r_px)

        elif isinstance(entity, ArcEntity):
            pts = entity.to_points(64)
            if len(pts) < 2:
                return
            path = QPainterPath()
            sp = self.world_to_screen(pts[0][0], pts[0][1])
            path.moveTo(sp)
            for p in pts[1:]:
                spt = self.world_to_screen(p[0], p[1])
                path.lineTo(spt)
            painter.drawPath(path)

    def _draw_selection_handles(self, painter: QPainter, entity: Entity):
        pen = QPen(QColor("#E55A28"), 1.5)
        pen.setCosmetic(True)
        brush = QBrush(QColor("#E55A28"))
        painter.setPen(pen)
        painter.setBrush(brush)
        size = 7

        def draw_handle(world_pt):
            sp = self.world_to_screen(world_pt[0], world_pt[1])
            painter.drawRect(int(sp.x()) - size // 2, int(sp.y()) - size // 2, size, size)

        if isinstance(entity, LineEntity):
            draw_handle(entity.start)
            draw_handle(entity.end)
        elif isinstance(entity, PolylineEntity):
            for p in entity.points:
                draw_handle(p)
        elif isinstance(entity, RectangleEntity):
            for c in entity._corners:
                draw_handle(c)
        elif isinstance(entity, CircleEntity):
            draw_handle(entity.center)
            draw_handle(entity.center + np.array([entity.radius, 0]))
        elif isinstance(entity, ArcEntity):
            draw_handle(entity.center)
            draw_handle(entity.to_points(32)[0])
            draw_handle(entity.to_points(32)[-1])
        elif isinstance(entity, SplineEntity):
            for cp in entity.control_points:
                draw_handle(cp)

    def _draw_tool_preview(self, painter: QPainter):
        pen = QPen(QColor("#E55A28"), 1.5, Qt.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        cur = self._snap_result.point if self._snap_result else self._cursor_world

        if self._tool == TOOL_LINE and self._tool_points:
            p1 = self.world_to_screen(*self._tool_points[0])
            p2 = self.world_to_screen(*cur)
            painter.drawLine(p1, p2)

        elif self._tool == TOOL_POLYLINE and self._tool_points:
            for i in range(len(self._tool_points) - 1):
                p1 = self.world_to_screen(*self._tool_points[i])
                p2 = self.world_to_screen(*self._tool_points[i + 1])
                painter.drawLine(p1, p2)
            last = self.world_to_screen(*self._tool_points[-1])
            painter.drawLine(last, self.world_to_screen(*cur))

        elif self._tool == TOOL_RECTANGLE and self._tool_points:
            p1 = self.world_to_screen(*self._tool_points[0])
            p2 = self.world_to_screen(*cur)
            x = min(p1.x(), p2.x())
            y = min(p1.y(), p2.y())
            w = abs(p2.x() - p1.x())
            h = abs(p2.y() - p1.y())
            painter.drawRect(int(x), int(y), int(w), int(h))

        elif self._tool == TOOL_CIRCLE and self._tool_points:
            center = self.world_to_screen(*self._tool_points[0])
            cur_screen = self.world_to_screen(*cur)
            dx = cur_screen.x() - center.x()
            dy = cur_screen.y() - center.y()
            r = math.sqrt(dx * dx + dy * dy)
            painter.drawEllipse(center, r, r)

        elif self._tool == TOOL_ARC:
            if self._arc_step == 1 and self._arc_center is not None:
                # Show radius line
                c = self.world_to_screen(*self._arc_center)
                cur_s = self.world_to_screen(*cur)
                painter.drawLine(c, cur_s)
            elif self._arc_step == 2 and self._arc_center is not None:
                # Show arc
                c = self._arc_center
                r = self._arc_radius
                end_angle = math.degrees(math.atan2(
                    float(cur[1] - c[1]), float(cur[0] - c[0]))) % 360
                dummy_arc = ArcEntity(c, r, self._arc_start_angle, end_angle)
                pts = dummy_arc.to_points(32)
                if len(pts) > 1:
                    path = QPainterPath()
                    sp = self.world_to_screen(pts[0][0], pts[0][1])
                    path.moveTo(sp)
                    for p in pts[1:]:
                        path.lineTo(self.world_to_screen(p[0], p[1]))
                    painter.drawPath(path)

        elif self._tool == TOOL_SPLINE and self._tool_points:
            if len(self._tool_points) > 1:
                dummy = SplineEntity(self._tool_points + [cur])
                pts = dummy.to_points()
                if len(pts) > 1:
                    path = QPainterPath()
                    sp = self.world_to_screen(pts[0][0], pts[0][1])
                    path.moveTo(sp)
                    for p in pts[1:]:
                        path.lineTo(self.world_to_screen(p[0], p[1]))
                    painter.drawPath(path)
            else:
                p1 = self.world_to_screen(*self._tool_points[0])
                painter.drawLine(p1, self.world_to_screen(*cur))

    def _draw_snap_indicator(self, painter: QPainter, point: np.ndarray):
        sp = self.world_to_screen(point[0], point[1])
        pen = QPen(QColor("#E55A28"), 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(sp, 6.0, 6.0)

    def _draw_rubber_band(self, painter: QPainter):
        pen = QPen(QColor("#E55A28"), 1.5, Qt.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(229, 90, 40, 30)))
        p1 = self._rubber_start_px
        p2 = self._rubber_end_px
        x = min(p1.x(), p2.x())
        y = min(p1.y(), p2.y())
        w = abs(p2.x() - p1.x())
        h = abs(p2.y() - p1.y())
        painter.drawRect(x, y, w, h)

    # ── Mouse events ─────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position() if hasattr(event, "position") else QPointF(event.pos())
        world = self.screen_to_world(pos.x(), pos.y())
        snapped = self._snap_result.point if self._snap_result else world

        # Middle mouse = pan
        if event.button() == Qt.MiddleButton:
            self._start_pan(pos.toPoint())
            return

        # Space+left = pan (handled in keyPress / mouseMoveEvent)
        if (event.button() == Qt.LeftButton and
                QApplication.keyboardModifiers() & Qt.Key_Space):
            self._start_pan(pos.toPoint())
            return

        if event.button() == Qt.LeftButton:
            self._handle_left_click(snapped, pos.toPoint(), event.modifiers())

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position() if hasattr(event, "position") else QPointF(event.pos())
        world = self.screen_to_world(pos.x(), pos.y())
        self._cursor_world = world

        # Update snap
        self._snap_result = self.snap_engine.snap(
            world, self.document.visible_entities(), self._scale
        )
        self.cursor_moved.emit(
            float(self._snap_result.point[0]),
            float(self._snap_result.point[1]),
        )

        # Pan
        if self._panning and self._pan_start_px and self._pan_start_offset:
            dx = pos.x() - self._pan_start_px.x()
            dy = pos.y() - self._pan_start_px.y()
            self._pan_offset = QPointF(
                self._pan_start_offset.x() + dx,
                self._pan_start_offset.y() + dy,
            )
            self.update()
            return

        # Rubber-band
        if self._rubber_start_px and self._tool == TOOL_SELECT:
            self._rubber_end_px = pos.toPoint()

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        pos = event.position() if hasattr(event, "position") else QPointF(event.pos())

        if event.button() == Qt.MiddleButton:
            self._panning = False
            return

        if self._panning:
            self._panning = False
            return

        if event.button() == Qt.LeftButton and self._tool == TOOL_SELECT:
            if self._rubber_start_px and self._rubber_end_px:
                self._finish_rubber_band_select(event.modifiers())
            self._rubber_start_px = None
            self._rubber_end_px = None
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self._tool == TOOL_POLYLINE and len(self._tool_points) >= 2:
                self._finish_polyline()
            elif self._tool == TOOL_SPLINE and len(self._tool_points) >= 2:
                self._finish_spline()

    def wheelEvent(self, event: QWheelEvent):
        pos = event.position() if hasattr(event, "position") else QPointF(event.pos())
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15

        old_world = self.screen_to_world(pos.x(), pos.y())
        self._scale = max(0.1, min(200.0, self._scale * factor))
        new_screen = self.world_to_screen(*old_world)
        self._pan_offset += QPointF(pos.x() - new_screen.x(), pos.y() - new_screen.y())
        self.zoom_changed.emit(self._scale)
        self.update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self._cancel_tool()
            self.set_tool(TOOL_SELECT)

    # ── Tool click handlers ──────────────────────────────

    def _handle_left_click(self, snapped: np.ndarray, screen_pos: QPoint, modifiers):
        if self._tool == TOOL_SELECT:
            self._handle_select_click(snapped, screen_pos, modifiers)

        elif self._tool == TOOL_LINE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                snap = self._snapshot_doc()
                entity = LineEntity(self._tool_points[0], snapped)
                self.document.add_entity(entity)
                self.document.commit_operation(snap)
                self.entity_added.emit(entity)
                self._tool_points = []
                self.update()

        elif self._tool == TOOL_POLYLINE:
            self._tool_points.append(snapped.copy())

        elif self._tool == TOOL_RECTANGLE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                snap = self._snapshot_doc()
                entity = RectangleEntity(self._tool_points[0], snapped)
                self.document.add_entity(entity)
                self.document.commit_operation(snap)
                self.entity_added.emit(entity)
                self._tool_points = []
                self.update()

        elif self._tool == TOOL_CIRCLE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                center = self._tool_points[0]
                radius = float(np.linalg.norm(snapped - center))
                if radius > 1e-6:
                    snap = self._snapshot_doc()
                    entity = CircleEntity(center, radius)
                    self.document.add_entity(entity)
                    self.document.commit_operation(snap)
                    self.entity_added.emit(entity)
                self._tool_points = []
                self.update()

        elif self._tool == TOOL_ARC:
            self._handle_arc_click(snapped)

        elif self._tool == TOOL_SPLINE:
            self._tool_points.append(snapped.copy())

    def _handle_select_click(self, snapped: np.ndarray, screen_pos: QPoint, modifiers):
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
            self._rubber_end_px = screen_pos
        self.update()

    def _handle_arc_click(self, snapped: np.ndarray):
        if self._arc_step == 0:
            self._arc_center = snapped.copy()
            self._arc_step = 1
        elif self._arc_step == 1:
            self._arc_radius = float(np.linalg.norm(snapped - self._arc_center))
            self._arc_start_angle = math.degrees(
                math.atan2(float(snapped[1] - self._arc_center[1]),
                           float(snapped[0] - self._arc_center[0]))
            ) % 360
            self._arc_step = 2
        elif self._arc_step == 2:
            end_angle = math.degrees(
                math.atan2(float(snapped[1] - self._arc_center[1]),
                           float(snapped[0] - self._arc_center[0]))
            ) % 360
            if self._arc_radius > 1e-6:
                snap = self._snapshot_doc()
                entity = ArcEntity(self._arc_center, self._arc_radius,
                                   self._arc_start_angle, end_angle)
                self.document.add_entity(entity)
                self.document.commit_operation(snap)
                self.entity_added.emit(entity)
            self._arc_step = 0
            self._arc_center = None
            self.update()

    def _finish_polyline(self):
        if len(self._tool_points) >= 2:
            snap = self._snapshot_doc()
            entity = PolylineEntity(self._tool_points)
            self.document.add_entity(entity)
            self.document.commit_operation(snap)
            self.entity_added.emit(entity)
        self._tool_points = []
        self.update()

    def _finish_spline(self):
        if len(self._tool_points) >= 2:
            snap = self._snapshot_doc()
            entity = SplineEntity(self._tool_points)
            self.document.add_entity(entity)
            self.document.commit_operation(snap)
            self.entity_added.emit(entity)
        self._tool_points = []
        self.update()

    # ── Rubber-band selection ────────────────────────────

    def _finish_rubber_band_select(self, modifiers):
        p1 = self._rubber_start_px
        p2 = self._rubber_end_px
        rect = QRect(
            min(p1.x(), p2.x()), min(p1.y(), p2.y()),
            abs(p2.x() - p1.x()), abs(p2.y() - p1.y()),
        )
        if not (modifiers & Qt.ShiftModifier):
            self.document.deselect_all()
        for entity in self.document.visible_entities():
            bb = entity.bounding_box()
            sp1 = self.world_to_screen(bb[0], bb[1])
            sp2 = self.world_to_screen(bb[2], bb[3])
            e_rect = QRect(
                int(min(sp1.x(), sp2.x())), int(min(sp1.y(), sp2.y())),
                int(abs(sp2.x() - sp1.x())), int(abs(sp2.y() - sp1.y())),
            )
            if rect.intersects(e_rect):
                entity.selected = True
        self.selection_changed.emit(self.document.selected_entities())
        self.update()

    # ── Hit test ─────────────────────────────────────────

    def _hit_test(self, world_pt: np.ndarray, threshold_px: float = 8.0) -> Optional[Entity]:
        threshold_world = threshold_px / self._scale
        best = None
        best_dist = float("inf")
        for entity in reversed(self.document.visible_entities()):
            nearest = entity.nearest_point(world_pt)
            dist = float(np.linalg.norm(world_pt - nearest))
            if dist < threshold_world and dist < best_dist:
                best_dist = dist
                best = entity
        return best

    # ── Helpers ──────────────────────────────────────────

    def _start_pan(self, screen_pos: QPoint):
        self._panning = True
        self._pan_start_px = screen_pos
        self._pan_start_offset = QPointF(self._pan_offset)
        self.setCursor(Qt.ClosedHandCursor)

    def _cancel_tool(self):
        self._tool_points = []
        self._arc_step = 0
        self._arc_center = None
        self._rubber_start_px = None
        self._rubber_end_px = None

    def _snapshot_doc(self):
        return self.document.begin_operation()
