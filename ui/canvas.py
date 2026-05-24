from __future__ import annotations
import math
import numpy as np
from typing import Optional
from PySide6.QtWidgets import QWidget, QApplication
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
)
from core.snap_engine import SnapEngine, SnapResult


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

# Axis colours
_X_COLOR      = QColor("#C04444")
_Y_COLOR      = QColor("#2266BB")
_ORIGIN_COLOR = QColor("#555555")


# ── Image overlay ─────────────────────────────────────────────
class ImageOverlay:
    """Reference image placed in world coordinates for tracing."""
    def __init__(self, pixmap: QPixmap, path: str,
                 world_x: float, world_y: float,
                 world_w: float, world_h: float,
                 opacity: float = 0.5):
        self.pixmap   = pixmap
        self.path     = path
        self.world_x  = float(world_x)   # top-left X (mm)
        self.world_y  = float(world_y)   # top-left Y (mm, +Y up)
        self.world_w  = float(world_w)   # width  (mm, positive)
        self.world_h  = float(world_h)   # height (mm, positive)
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

    def __init__(self, document: Document, snap_engine: SnapEngine, parent=None):
        super().__init__(parent)
        self.document    = document
        self.snap_engine = snap_engine

        # View
        self._scale: float = 5.0          # pixels per mm
        self._pan_offset   = QPointF(0.0, 0.0)
        self._initialized  = False        # set origin to center on first show

        # Grid / axes
        self.grid_visible: bool = True
        self.axes_visible: bool = True
        self.grid_size: float   = 10.0    # mm

        # Images
        self._images: list[ImageOverlay]   = []
        self._dragging_image: Optional[ImageOverlay] = None
        self._drag_img_offset: np.ndarray  = np.zeros(2)

        # Tool state
        self._tool: str              = TOOL_SELECT
        self._tool_points: list[np.ndarray] = []
        self._polygon_sides: int     = 6

        # Arc state (3-click)
        self._arc_step: int          = 0
        self._arc_center: Optional[np.ndarray] = None
        self._arc_radius: float      = 0.0
        self._arc_start_angle: float = 0.0

        # Groove state (3-click)
        self._groove_step: int = 0
        self._groove_c1: Optional[np.ndarray] = None
        self._groove_c2: Optional[np.ndarray] = None

        # Snap / cursor
        self._snap_result: Optional[SnapResult] = None
        self._cursor_world = np.zeros(2)

        # Pan
        self._panning           = False
        self._pan_start_px: Optional[QPoint]  = None
        self._pan_start_offset: Optional[QPointF] = None

        # Rubber-band select
        self._rubber_start_px: Optional[QPoint] = None
        self._rubber_end_px:   Optional[QPoint] = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.ArrowCursor)

    # ── Lifecycle ─────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            # Place origin at the centre of the canvas on first show
            self._pan_offset  = QPointF(self.width() / 2.0, self.height() / 2.0)
            self._initialized = True

    # ── Public API ────────────────────────────────────────────

    def set_tool(self, tool: str):
        self._cancel_tool()
        self._tool = tool
        self.setCursor(Qt.ArrowCursor if tool == TOOL_SELECT else Qt.CrossCursor)
        self.tool_changed.emit(tool)
        self.update()

    def set_polygon_sides(self, n: int):
        self._polygon_sides = max(3, n)

    def set_grid_visible(self, v: bool):
        self.grid_visible = v; self.update()

    def set_axes_visible(self, v: bool):
        self.axes_visible = v; self.update()

    def center_origin(self):
        """Reset view so world (0,0) is at the screen centre."""
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

        # 0. White background
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        # 1. Grid
        if self.grid_visible:
            self._draw_grid(painter)

        # 2. Reference images (semi-transparent, under entities)
        self._draw_images(painter)

        # 3. Origin axes (over images, under entities)
        if self.axes_visible:
            self._draw_origin_axes(painter)

        # 4. Geometry entities
        for entity in self.document.visible_entities():
            self._draw_entity(painter, entity)

        # 5. Selection handles
        for entity in self.document.selected_entities():
            self._draw_selection_handles(painter, entity)

        # 6. Active-tool rubber-band preview
        self._draw_tool_preview(painter)

        # 7. Snap indicator
        if self._snap_result and self._snap_result.snap_type != "none":
            self._draw_snap_indicator(painter, self._snap_result.point)

        # 8. Rubber-band selection rect
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

            # Selection border + corner handles
            if img.selected:
                frect = QRectF(tl, br)
                sel_pen = QPen(QColor("#E55A28"), 1.8, Qt.DashLine)
                sel_pen.setCosmetic(True)
                painter.setPen(sel_pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(frect)
                # Corner handles
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#E55A28"))
                for corner in (frect.topLeft(), frect.topRight(),
                               frect.bottomLeft(), frect.bottomRight()):
                    painter.drawRect(QRectF(corner.x() - 5, corner.y() - 5, 10, 10))
                # Path label (file name)
                import os as _os
                painter.setPen(QColor("#E55A28"))
                lbl_font = QFont("Segoe UI", 8)
                painter.setFont(lbl_font)
                painter.drawText(QPointF(tl.x() + 4, tl.y() + 14),
                                 _os.path.basename(img.path))

    # ── Origin axes ───────────────────────────────────────────

    def _draw_origin_axes(self, painter: QPainter):
        sw, sh = float(self.width()), float(self.height())
        ARROW  = 12.0
        font   = QFont("Segoe UI", 8, QFont.Bold)

        origin_s = self.world_to_screen(0.0, 0.0)
        ox, oy   = origin_s.x(), origin_s.y()

        # ── X-axis ────────────────────────────────────────────
        if 0 <= oy <= sh:
            pen = QPen(_X_COLOR, 1.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(QPointF(0.0, oy), QPointF(sw, oy))

            # Arrow at right edge → +X
            tip = QPointF(sw - 2, oy)
            painter.setPen(Qt.NoPen)
            painter.setBrush(_X_COLOR)
            painter.drawPolygon(QPolygonF([
                tip,
                QPointF(sw - 2 - ARROW, oy - ARROW * 0.4),
                QPointF(sw - 2 - ARROW, oy + ARROW * 0.4),
            ]))
            painter.setFont(font)
            painter.setPen(_X_COLOR)
            painter.drawText(QPointF(sw - 2 - ARROW - 26, oy - 5), "+X")

            # Tick labels
            self._draw_x_ticks(painter, oy, sw, sh)

        # ── Y-axis ────────────────────────────────────────────
        if 0 <= ox <= sw:
            pen = QPen(_Y_COLOR, 1.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(QPointF(ox, 0.0), QPointF(ox, sh))

            # Arrow at top edge ↑ +Y
            tip = QPointF(ox, 2.0)
            painter.setPen(Qt.NoPen)
            painter.setBrush(_Y_COLOR)
            painter.drawPolygon(QPolygonF([
                tip,
                QPointF(ox - ARROW * 0.4, 2.0 + ARROW),
                QPointF(ox + ARROW * 0.4, 2.0 + ARROW),
            ]))
            painter.setFont(font)
            painter.setPen(_Y_COLOR)
            painter.drawText(QPointF(ox + 5, 2.0 + ARROW + 14), "+Y")

            # Tick labels
            self._draw_y_ticks(painter, ox, sw, sh)

        # ── Origin dot ────────────────────────────────────────
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
        font    = QFont("Segoe UI", 7)
        painter.setFont(font)
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
        font  = QFont("Segoe UI", 7)
        painter.setFont(font)
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
        pen       = QPen(color, 2.0 if entity.selected else 1.2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if isinstance(entity, LineEntity):
            painter.drawLine(self.world_to_screen(*entity.start),
                             self.world_to_screen(*entity.end))

        elif isinstance(entity, CircleEntity):
            c = self.world_to_screen(*entity.center)
            painter.drawEllipse(c, entity.radius * self._scale,
                                    entity.radius * self._scale)

        elif isinstance(entity, EllipseEntity):
            c    = self.world_to_screen(*entity.center)
            rx   = entity.rx * self._scale
            ry   = entity.ry * self._scale
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
            for p in pts[1:]:
                path.lineTo(self.world_to_screen(p[0], p[1]))
            painter.drawPath(path)

        elif isinstance(entity, (PolylineEntity, RectangleEntity, SplineEntity,
                                  PolygonEntity, GrooveEntity)):
            pts = entity.to_points()
            if len(pts) < 2: return
            path = QPainterPath()
            path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
            for p in pts[1:]:
                path.lineTo(self.world_to_screen(p[0], p[1]))
            closed = isinstance(entity, (RectangleEntity, PolygonEntity, GrooveEntity)) or \
                     (isinstance(entity, PolylineEntity) and entity.closed)
            if closed:
                path.closeSubpath()
            painter.drawPath(path)

    # ── Selection handles ─────────────────────────────────────

    def _draw_selection_handles(self, painter: QPainter, entity: Entity):
        pen = QPen(QColor("#E55A28"), 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor("#E55A28"))
        sz = 7

        def handle(world_pt):
            sp = self.world_to_screen(float(world_pt[0]), float(world_pt[1]))
            painter.drawRect(int(sp.x()) - sz // 2, int(sp.y()) - sz // 2, sz, sz)

        if isinstance(entity, LineEntity):
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
        pen = QPen(QColor("#E55A28"), 1.5, Qt.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        cur = self._snap_result.point if self._snap_result else self._cursor_world
        t   = self._tool

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
            painter.drawEllipse(c, math.hypot(c2.x()-c.x(), c2.y()-c.y()),
                                   math.hypot(c2.x()-c.x(), c2.y()-c.y()))

        elif t == TOOL_ARC:
            if self._arc_step == 1 and self._arc_center is not None:
                painter.drawLine(self.world_to_screen(*self._arc_center),
                                 self.world_to_screen(*cur))
            elif self._arc_step == 2 and self._arc_center is not None:
                ea = math.degrees(math.atan2(float(cur[1] - self._arc_center[1]),
                                             float(cur[0] - self._arc_center[0]))) % 360
                dummy = ArcEntity(self._arc_center, self._arc_radius,
                                  self._arc_start_angle, ea)
                pts = dummy.to_points(32)
                if len(pts) > 1:
                    path = QPainterPath()
                    path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
                    for p in pts[1:]: path.lineTo(self.world_to_screen(p[0], p[1]))
                    painter.drawPath(path)

        elif t == TOOL_SPLINE and self._tool_points:
            dummy = SplineEntity(self._tool_points + [cur])
            pts   = dummy.to_points()
            if len(pts) > 1:
                path = QPainterPath()
                path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
                for p in pts[1:]: path.lineTo(self.world_to_screen(p[0], p[1]))
                painter.drawPath(path)
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
                pts   = dummy.to_points()
                path  = QPainterPath()
                path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
                for p in pts[1:]: path.lineTo(self.world_to_screen(p[0], p[1]))
                path.closeSubpath()
                painter.drawPath(path)

        elif t == TOOL_SEMICIRCLE and self._tool_points:
            center = self._tool_points[0]
            r = float(np.linalg.norm(cur - center))
            if r > 1e-6:
                bump  = math.degrees(math.atan2(float(cur[1]-center[1]),
                                                float(cur[0]-center[0])))
                dummy = SemiCircleEntity(center, r, (bump - 90) % 360)
                pts   = dummy.to_points(32)
                path  = QPainterPath()
                path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
                for p in pts[1:]: path.lineTo(self.world_to_screen(p[0], p[1]))
                painter.drawPath(path)

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
                    pts   = dummy.to_points(32)
                    path  = QPainterPath()
                    path.moveTo(self.world_to_screen(pts[0][0], pts[0][1]))
                    for p in pts[1:]: path.lineTo(self.world_to_screen(p[0], p[1]))
                    painter.drawPath(path)

    def _draw_snap_indicator(self, painter: QPainter, point: np.ndarray):
        sp  = self.world_to_screen(point[0], point[1])
        pen = QPen(QColor("#E55A28"), 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(sp, 6.0, 6.0)

    def _draw_rubber_band(self, painter: QPainter):
        pen = QPen(QColor("#E55A28"), 1.5, Qt.DashLine)
        pen.setCosmetic(True)
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

        if event.button() == Qt.LeftButton and \
                QApplication.keyboardModifiers() & Qt.Key_Space:
            self._start_pan(pos.toPoint()); return

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

        # Pan
        if self._panning and self._pan_start_px and self._pan_start_offset:
            dx = pos.x() - self._pan_start_px.x()
            dy = pos.y() - self._pan_start_px.y()
            self._pan_offset = QPointF(self._pan_start_offset.x() + dx,
                                       self._pan_start_offset.y() + dy)
            self.update(); return

        # Image drag
        if self._dragging_image is not None:
            new_pos = world - self._drag_img_offset
            self._dragging_image.world_x = float(new_pos[0])
            self._dragging_image.world_y = float(new_pos[1])
            self.update(); return

        # Rubber-band
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
        if event.key() == Qt.Key_Escape:
            self._cancel_tool()
            self.set_tool(TOOL_SELECT)

    # ── Tool click handlers ───────────────────────────────────

    def _handle_left_click(self, snapped: np.ndarray, raw_world: np.ndarray,
                            screen_pos: QPoint, modifiers):
        t = self._tool

        if t == TOOL_SELECT:
            self._handle_select_click(snapped, raw_world, screen_pos, modifiers)

        elif t == TOOL_LINE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                self._commit(LineEntity(self._tool_points[0], snapped))
                self._tool_points = []

        elif t == TOOL_POLYLINE:
            self._tool_points.append(snapped.copy())

        elif t == TOOL_RECTANGLE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                self._commit(RectangleEntity(self._tool_points[0], snapped))
                self._tool_points = []

        elif t == TOOL_ELLIPSE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                c1 = self._tool_points[0]
                center = (c1 + snapped) / 2
                rx = abs(snapped[0] - c1[0]) / 2
                ry = abs(snapped[1] - c1[1]) / 2
                if rx > 1e-6 and ry > 1e-6:
                    self._commit(EllipseEntity(center, rx, ry))
                self._tool_points = []

        elif t == TOOL_CIRCLE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                r = float(np.linalg.norm(snapped - self._tool_points[0]))
                if r > 1e-6:
                    self._commit(CircleEntity(self._tool_points[0], r))
                self._tool_points = []

        elif t == TOOL_ARC:
            self._handle_arc_click(snapped)

        elif t == TOOL_SPLINE:
            self._tool_points.append(snapped.copy())

        elif t == TOOL_POLYGON:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                center = self._tool_points[0]
                r = float(np.linalg.norm(snapped - center))
                if r > 1e-6:
                    rot = math.degrees(math.atan2(float(snapped[1]-center[1]),
                                                  float(snapped[0]-center[0])))
                    self._commit(PolygonEntity(center, self._polygon_sides, r, rot))
                self._tool_points = []

        elif t == TOOL_SEMICIRCLE:
            if not self._tool_points:
                self._tool_points = [snapped.copy()]
            else:
                center = self._tool_points[0]
                r = float(np.linalg.norm(snapped - center))
                if r > 1e-6:
                    bump = math.degrees(math.atan2(float(snapped[1]-center[1]),
                                                   float(snapped[0]-center[0])))
                    self._commit(SemiCircleEntity(center, r, (bump - 90) % 360))
                self._tool_points = []

        elif t == TOOL_GROOVE:
            self._handle_groove_click(snapped)

        self.update()

    def _handle_select_click(self, snapped, raw_world, screen_pos, modifiers):
        # 1. Check images first
        img_hit = self._hit_test_image(raw_world)
        if img_hit and not img_hit.locked:
            for i in self._images: i.selected = False
            img_hit.selected = True
            self._dragging_image   = img_hit
            self._drag_img_offset  = raw_world - np.array([img_hit.world_x, img_hit.world_y])
            self.document.deselect_all()
            self.selection_changed.emit([])
            self.update(); return

        # 2. Deselect images
        for i in self._images: i.selected = False

        # 3. Entity hit test
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

    def _handle_arc_click(self, snapped):
        if self._arc_step == 0:
            self._arc_center = snapped.copy(); self._arc_step = 1
        elif self._arc_step == 1:
            self._arc_radius = float(np.linalg.norm(snapped - self._arc_center))
            self._arc_start_angle = math.degrees(
                math.atan2(float(snapped[1]-self._arc_center[1]),
                           float(snapped[0]-self._arc_center[0]))) % 360
            self._arc_step = 2
        elif self._arc_step == 2:
            ea = math.degrees(math.atan2(float(snapped[1]-self._arc_center[1]),
                                         float(snapped[0]-self._arc_center[0]))) % 360
            if self._arc_radius > 1e-6:
                self._commit(ArcEntity(self._arc_center, self._arc_radius,
                                       self._arc_start_angle, ea))
            self._arc_step = 0; self._arc_center = None

    def _handle_groove_click(self, snapped):
        if self._groove_step == 0:
            self._groove_c1 = snapped.copy(); self._groove_step = 1
        elif self._groove_step == 1:
            self._groove_c2 = snapped.copy(); self._groove_step = 2
        elif self._groove_step == 2:
            c1, c2 = self._groove_c1, self._groove_c2
            axis = c2 - c1
            aln  = float(np.linalg.norm(axis))
            if aln > 1e-6:
                perp = np.array([-axis[1], axis[0]]) / aln
                r    = max(abs(float(np.dot(snapped - (c1+c2)/2, perp))), 0.5)
                self._commit(GrooveEntity(c1, c2, r))
            self._groove_step = 0
            self._groove_c1 = self._groove_c2 = None

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

    # ── Helpers ───────────────────────────────────────────────

    def _commit(self, entity: Entity):
        snap = self.document.begin_operation()
        self.document.add_entity(entity)
        self.document.commit_operation(snap)
        self.entity_added.emit(entity)

    def _start_pan(self, screen_pos: QPoint):
        self._panning          = True
        self._pan_start_px     = screen_pos
        self._pan_start_offset = QPointF(self._pan_offset)
        self.setCursor(Qt.ClosedHandCursor)

    def _cancel_tool(self):
        self._tool_points = []
        self._arc_step    = 0;   self._arc_center   = None
        self._groove_step = 0;   self._groove_c1    = self._groove_c2 = None
        self._rubber_start_px = self._rubber_end_px = None
        self._dragging_image  = None
