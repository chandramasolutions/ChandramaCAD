from __future__ import annotations
import math
import numpy as np
from typing import Optional


_id_counter = 0


def _next_id() -> int:
    global _id_counter
    _id_counter += 1
    return _id_counter


class Entity:
    def __init__(self):
        self.id: int = _next_id()
        self.layer: str = "Default"
        self.color: Optional[str] = None  # None = use layer colour
        self.selected: bool = False

    def bounding_box(self) -> tuple[float, float, float, float]:
        raise NotImplementedError

    def nearest_point(self, pt: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def translate(self, dx: float, dy: float) -> None:
        raise NotImplementedError

    def rotate(self, angle_deg: float, origin: np.ndarray) -> None:
        raise NotImplementedError

    def scale(self, factor: float, origin: np.ndarray) -> None:
        raise NotImplementedError

    def to_dxf(self, msp) -> None:
        raise NotImplementedError

    def to_points(self, n: int = 200) -> np.ndarray:
        raise NotImplementedError

    def clone(self) -> "Entity":
        raise NotImplementedError

    def _rotate_point(self, pt: np.ndarray, angle_deg: float, origin: np.ndarray) -> np.ndarray:
        a = math.radians(angle_deg)
        cos_a, sin_a = math.cos(a), math.sin(a)
        p = pt - origin
        return np.array([
            p[0] * cos_a - p[1] * sin_a,
            p[0] * sin_a + p[1] * cos_a,
        ]) + origin

    def _scale_point(self, pt: np.ndarray, factor: float, origin: np.ndarray) -> np.ndarray:
        return origin + (pt - origin) * factor


class LineEntity(Entity):
    def __init__(self, start: np.ndarray, end: np.ndarray):
        super().__init__()
        self.start = np.array(start, dtype=float)
        self.end = np.array(end, dtype=float)

    def bounding_box(self):
        return (min(self.start[0], self.end[0]),
                min(self.start[1], self.end[1]),
                max(self.start[0], self.end[0]),
                max(self.start[1], self.end[1]))

    def nearest_point(self, pt):
        d = self.end - self.start
        length_sq = float(np.dot(d, d))
        if length_sq < 1e-12:
            return self.start.copy()
        t = float(np.dot(pt - self.start, d)) / length_sq
        t = max(0.0, min(1.0, t))
        return self.start + t * d

    def translate(self, dx, dy):
        self.start += [dx, dy]
        self.end += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.start = self._rotate_point(self.start, angle_deg, origin)
        self.end = self._rotate_point(self.end, angle_deg, origin)

    def scale(self, factor, origin):
        self.start = self._scale_point(self.start, factor, origin)
        self.end = self._scale_point(self.end, factor, origin)

    def to_dxf(self, msp):
        msp.add_line(
            start=(float(self.start[0]), float(self.start[1]), 0),
            end=(float(self.end[0]), float(self.end[1]), 0),
            dxfattribs={"layer": self.layer},
        )

    def to_points(self, n=2):
        return np.array([self.start, self.end])

    def length(self) -> float:
        return float(np.linalg.norm(self.end - self.start))

    def clone(self):
        e = LineEntity(self.start.copy(), self.end.copy())
        e.layer = self.layer
        e.color = self.color
        return e


class PolylineEntity(Entity):
    def __init__(self, points: list[np.ndarray], closed: bool = False):
        super().__init__()
        self.points = [np.array(p, dtype=float) for p in points]
        self.closed = closed

    def bounding_box(self):
        if not self.points:
            return (0, 0, 0, 0)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def nearest_point(self, pt):
        best = None
        best_dist = float("inf")
        pts = self.points + ([self.points[0]] if self.closed else [])
        for i in range(len(pts) - 1):
            seg_start = pts[i]
            seg_end = pts[i + 1]
            d = seg_end - seg_start
            length_sq = float(np.dot(d, d))
            if length_sq < 1e-12:
                candidate = seg_start.copy()
            else:
                t = max(0.0, min(1.0, float(np.dot(pt - seg_start, d)) / length_sq))
                candidate = seg_start + t * d
            dist = float(np.linalg.norm(pt - candidate))
            if dist < best_dist:
                best_dist = dist
                best = candidate
        return best if best is not None else self.points[0].copy()

    def translate(self, dx, dy):
        for p in self.points:
            p += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.points = [self._rotate_point(p, angle_deg, origin) for p in self.points]

    def scale(self, factor, origin):
        self.points = [self._scale_point(p, factor, origin) for p in self.points]

    def to_dxf(self, msp):
        pts = [(float(p[0]), float(p[1])) for p in self.points]
        msp.add_lwpolyline(pts, close=self.closed, dxfattribs={"layer": self.layer})

    def to_points(self, n=200):
        return np.array(self.points)

    def clone(self):
        e = PolylineEntity([p.copy() for p in self.points], self.closed)
        e.layer = self.layer
        e.color = self.color
        return e


class RectangleEntity(Entity):
    def __init__(self, corner1: np.ndarray, corner2: np.ndarray):
        super().__init__()
        self.corner1 = np.array(corner1, dtype=float)
        self.corner2 = np.array(corner2, dtype=float)

    @property
    def _corners(self) -> list[np.ndarray]:
        x1, y1 = self.corner1
        x2, y2 = self.corner2
        return [
            np.array([x1, y1]),
            np.array([x2, y1]),
            np.array([x2, y2]),
            np.array([x1, y2]),
        ]

    def bounding_box(self):
        x1, y1 = self.corner1
        x2, y2 = self.corner2
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    def nearest_point(self, pt):
        corners = self._corners
        best = corners[0].copy()
        best_dist = float(np.linalg.norm(pt - best))
        for c in corners[1:]:
            d = float(np.linalg.norm(pt - c))
            if d < best_dist:
                best_dist = d
                best = c.copy()
        return best

    def translate(self, dx, dy):
        self.corner1 += [dx, dy]
        self.corner2 += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.corner1 = self._rotate_point(self.corner1, angle_deg, origin)
        self.corner2 = self._rotate_point(self.corner2, angle_deg, origin)

    def scale(self, factor, origin):
        self.corner1 = self._scale_point(self.corner1, factor, origin)
        self.corner2 = self._scale_point(self.corner2, factor, origin)

    def to_dxf(self, msp):
        x1, y1 = self.corner1
        x2, y2 = self.corner2
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": self.layer})

    def to_points(self, n=4):
        corners = self._corners
        return np.array(corners + [corners[0]])

    def clone(self):
        e = RectangleEntity(self.corner1.copy(), self.corner2.copy())
        e.layer = self.layer
        e.color = self.color
        return e


class CircleEntity(Entity):
    def __init__(self, center: np.ndarray, radius: float):
        super().__init__()
        self.center = np.array(center, dtype=float)
        self.radius = float(radius)

    def bounding_box(self):
        cx, cy = self.center
        r = self.radius
        return (cx - r, cy - r, cx + r, cy + r)

    def nearest_point(self, pt):
        d = pt - self.center
        dist = float(np.linalg.norm(d))
        if dist < 1e-12:
            return self.center + np.array([self.radius, 0])
        return self.center + d / dist * self.radius

    def translate(self, dx, dy):
        self.center += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.center = self._rotate_point(self.center, angle_deg, origin)

    def scale(self, factor, origin):
        self.center = self._scale_point(self.center, factor, origin)
        self.radius *= factor

    def to_dxf(self, msp):
        msp.add_circle(
            center=(float(self.center[0]), float(self.center[1]), 0),
            radius=self.radius,
            dxfattribs={"layer": self.layer},
        )

    def to_points(self, n=200):
        angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
        return self.center + self.radius * np.column_stack([np.cos(angles), np.sin(angles)])

    def clone(self):
        e = CircleEntity(self.center.copy(), self.radius)
        e.layer = self.layer
        e.color = self.color
        return e


class ArcEntity(Entity):
    def __init__(self, center: np.ndarray, radius: float,
                 start_angle: float, end_angle: float):
        super().__init__()
        self.center = np.array(center, dtype=float)
        self.radius = float(radius)
        self.start_angle = float(start_angle)  # degrees
        self.end_angle = float(end_angle)       # degrees

    def _angle_span(self) -> float:
        span = self.end_angle - self.start_angle
        if span <= 0:
            span += 360.0
        return span

    def bounding_box(self):
        cx, cy = self.center
        r = self.radius
        pts = self.to_points(64)
        xs, ys = pts[:, 0], pts[:, 1]
        return (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))

    def nearest_point(self, pt):
        d = pt - self.center
        angle = math.degrees(math.atan2(float(d[1]), float(d[0]))) % 360
        sa = self.start_angle % 360
        ea = self.end_angle % 360
        span = self._angle_span()
        rel = (angle - sa) % 360
        if rel <= span:
            clamped = angle
        else:
            mid = (sa + span / 2) % 360
            if abs(rel - span) < abs(rel):
                clamped = ea
            else:
                clamped = sa
        rad = math.radians(clamped)
        return self.center + self.radius * np.array([math.cos(rad), math.sin(rad)])

    def translate(self, dx, dy):
        self.center += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.center = self._rotate_point(self.center, angle_deg, origin)
        self.start_angle = (self.start_angle + angle_deg) % 360
        self.end_angle = (self.end_angle + angle_deg) % 360

    def scale(self, factor, origin):
        self.center = self._scale_point(self.center, factor, origin)
        self.radius *= abs(factor)

    def to_dxf(self, msp):
        msp.add_arc(
            center=(float(self.center[0]), float(self.center[1]), 0),
            radius=self.radius,
            start_angle=self.start_angle,
            end_angle=self.end_angle,
            dxfattribs={"layer": self.layer},
        )

    def to_points(self, n=64):
        span = self._angle_span()
        angles = np.linspace(
            math.radians(self.start_angle),
            math.radians(self.start_angle + span),
            max(n, 2),
        )
        return self.center + self.radius * np.column_stack([np.cos(angles), np.sin(angles)])

    def clone(self):
        e = ArcEntity(self.center.copy(), self.radius, self.start_angle, self.end_angle)
        e.layer = self.layer
        e.color = self.color
        return e


class SplineEntity(Entity):
    def __init__(self, control_points: list[np.ndarray]):
        super().__init__()
        self.control_points = [np.array(p, dtype=float) for p in control_points]

    def bounding_box(self):
        pts = self.to_points()
        if len(pts) == 0:
            return (0, 0, 0, 0)
        return (float(pts[:, 0].min()), float(pts[:, 1].min()),
                float(pts[:, 0].max()), float(pts[:, 1].max()))

    def nearest_point(self, pt):
        pts = self.to_points()
        dists = np.linalg.norm(pts - pt, axis=1)
        return pts[int(np.argmin(dists))].copy()

    def translate(self, dx, dy):
        for p in self.control_points:
            p += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.control_points = [self._rotate_point(p, angle_deg, origin) for p in self.control_points]

    def scale(self, factor, origin):
        self.control_points = [self._scale_point(p, factor, origin) for p in self.control_points]

    def to_dxf(self, msp):
        pts = [(float(p[0]), float(p[1]), 0) for p in self.control_points]
        msp.add_spline(fit_points=pts, dxfattribs={"layer": self.layer})

    def to_points(self, n=200) -> np.ndarray:
        cps = self.control_points
        if len(cps) < 2:
            return np.array(cps) if cps else np.zeros((0, 2))
        if len(cps) == 2:
            return np.array([cps[0], cps[1]])
        # Catmull-Rom spline through control points
        pts_out = []
        for i in range(len(cps) - 1):
            p0 = cps[max(0, i - 1)]
            p1 = cps[i]
            p2 = cps[i + 1]
            p3 = cps[min(len(cps) - 1, i + 2)]
            seg_n = max(4, n // (len(cps) - 1))
            for j in range(seg_n):
                t = j / seg_n
                t2, t3 = t * t, t * t * t
                pt = 0.5 * (
                    2 * p1
                    + (-p0 + p2) * t
                    + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
                )
                pts_out.append(pt)
        pts_out.append(cps[-1])
        return np.array(pts_out)

    def clone(self):
        e = SplineEntity([p.copy() for p in self.control_points])
        e.layer = self.layer
        e.color = self.color
        return e


# ══════════════════════════════════════════════════════════
# EXTENDED SHAPE ENTITIES
# ══════════════════════════════════════════════════════════

class PolygonEntity(Entity):
    """Regular N-sided polygon defined by center and circumradius."""
    def __init__(self, center: np.ndarray, n_sides: int,
                 circumradius: float, rotation_deg: float = 90.0):
        super().__init__()
        self.center = np.array(center, dtype=float)
        self.n_sides = max(3, int(n_sides))
        self.circumradius = float(circumradius)
        self.rotation_deg = float(rotation_deg)

    def _vertices(self) -> list[np.ndarray]:
        base = math.radians(self.rotation_deg)
        step = 2 * math.pi / self.n_sides
        return [
            self.center + self.circumradius * np.array([
                math.cos(base + i * step),
                math.sin(base + i * step),
            ])
            for i in range(self.n_sides)
        ]

    def bounding_box(self):
        pts = np.array(self._vertices())
        return (float(pts[:, 0].min()), float(pts[:, 1].min()),
                float(pts[:, 0].max()), float(pts[:, 1].max()))

    def nearest_point(self, pt):
        verts = self._vertices()
        best = verts[0].copy()
        best_dist = float(np.linalg.norm(pt - best))
        for v in verts[1:]:
            d = float(np.linalg.norm(pt - v))
            if d < best_dist:
                best_dist = d
                best = v.copy()
        return best

    def translate(self, dx, dy):
        self.center += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.center = self._rotate_point(self.center, angle_deg, origin)
        self.rotation_deg = (self.rotation_deg + angle_deg) % 360

    def scale(self, factor, origin):
        self.center = self._scale_point(self.center, factor, origin)
        self.circumradius *= abs(factor)

    def to_dxf(self, msp):
        verts = [(float(v[0]), float(v[1])) for v in self._vertices()]
        msp.add_lwpolyline(verts, close=True, dxfattribs={"layer": self.layer})

    def to_points(self, n=None) -> np.ndarray:
        verts = self._vertices()
        return np.array(verts + [verts[0]])

    def clone(self):
        e = PolygonEntity(self.center.copy(), self.n_sides,
                          self.circumradius, self.rotation_deg)
        e.layer = self.layer
        e.color = self.color
        return e


class EllipseEntity(Entity):
    """Axis-aligned or rotated ellipse."""
    def __init__(self, center: np.ndarray, rx: float, ry: float,
                 rotation_deg: float = 0.0):
        super().__init__()
        self.center = np.array(center, dtype=float)
        self.rx = float(rx)
        self.ry = float(ry)
        self.rotation_deg = float(rotation_deg)

    def bounding_box(self):
        pts = self.to_points(64)
        return (float(pts[:, 0].min()), float(pts[:, 1].min()),
                float(pts[:, 0].max()), float(pts[:, 1].max()))

    def nearest_point(self, pt):
        pts = self.to_points(128)
        dists = np.linalg.norm(pts - pt, axis=1)
        return pts[int(np.argmin(dists))].copy()

    def translate(self, dx, dy):
        self.center += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.center = self._rotate_point(self.center, angle_deg, origin)
        self.rotation_deg = (self.rotation_deg + angle_deg) % 360

    def scale(self, factor, origin):
        self.center = self._scale_point(self.center, factor, origin)
        self.rx *= abs(factor)
        self.ry *= abs(factor)

    def to_dxf(self, msp):
        rot = math.radians(self.rotation_deg)
        major_axis = (self.rx * math.cos(rot), self.rx * math.sin(rot), 0)
        ratio = self.ry / self.rx if self.rx > 1e-12 else 1.0
        msp.add_ellipse(
            center=(float(self.center[0]), float(self.center[1]), 0),
            major_axis=major_axis,
            ratio=ratio,
            dxfattribs={"layer": self.layer},
        )

    def to_points(self, n=128) -> np.ndarray:
        angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
        rot = math.radians(self.rotation_deg)
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        xs = self.rx * np.cos(angles)
        ys = self.ry * np.sin(angles)
        x_rot = xs * cos_r - ys * sin_r + self.center[0]
        y_rot = xs * sin_r + ys * cos_r + self.center[1]
        return np.column_stack([x_rot, y_rot])

    def clone(self):
        e = EllipseEntity(self.center.copy(), self.rx, self.ry, self.rotation_deg)
        e.layer = self.layer
        e.color = self.color
        return e


class SemiCircleEntity(Entity):
    """
    Half-circle.  flat_angle is the angle (degrees) pointing to the flat-edge
    start.  The arc spans flat_angle → flat_angle+180 (CCW), bump faces
    flat_angle+90.  e.g. flat_angle=0 → horizontal flat at bottom, bump up.
    """
    def __init__(self, center: np.ndarray, radius: float, flat_angle: float = 0.0):
        super().__init__()
        self.center = np.array(center, dtype=float)
        self.radius = float(radius)
        self.flat_angle = float(flat_angle)

    def _arc_points(self, n: int = 64) -> np.ndarray:
        angles = np.linspace(
            math.radians(self.flat_angle),
            math.radians(self.flat_angle + 180),
            max(n, 4),
        )
        return self.center + self.radius * np.column_stack([np.cos(angles), np.sin(angles)])

    def bounding_box(self):
        pts = self._arc_points()
        return (float(pts[:, 0].min()), float(pts[:, 1].min()),
                float(pts[:, 0].max()), float(pts[:, 1].max()))

    def nearest_point(self, pt):
        pts = self._arc_points()
        dists = np.linalg.norm(pts - pt, axis=1)
        return pts[int(np.argmin(dists))].copy()

    def translate(self, dx, dy):
        self.center += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.center = self._rotate_point(self.center, angle_deg, origin)
        self.flat_angle = (self.flat_angle + angle_deg) % 360

    def scale(self, factor, origin):
        self.center = self._scale_point(self.center, factor, origin)
        self.radius *= abs(factor)

    def to_dxf(self, msp):
        msp.add_arc(
            center=(float(self.center[0]), float(self.center[1]), 0),
            radius=self.radius,
            start_angle=self.flat_angle,
            end_angle=(self.flat_angle + 180) % 360,
            dxfattribs={"layer": self.layer},
        )
        # chord line
        fa = math.radians(self.flat_angle)
        fb = math.radians(self.flat_angle + 180)
        p1 = self.center + self.radius * np.array([math.cos(fa), math.sin(fa)])
        p2 = self.center + self.radius * np.array([math.cos(fb), math.sin(fb)])
        msp.add_line((float(p1[0]), float(p1[1]), 0),
                     (float(p2[0]), float(p2[1]), 0),
                     dxfattribs={"layer": self.layer})

    def to_points(self, n=64) -> np.ndarray:
        arc = self._arc_points(n)
        return np.vstack([arc, arc[0]])   # close with chord

    def clone(self):
        e = SemiCircleEntity(self.center.copy(), self.radius, self.flat_angle)
        e.layer = self.layer
        e.color = self.color
        return e


class GrooveEntity(Entity):
    """
    Slot / oblong groove: two semicircles at each end joined by parallel lines.
    center1/center2 = semicircle centres; radius = half-width.
    """
    def __init__(self, center1: np.ndarray, center2: np.ndarray, radius: float):
        super().__init__()
        self.center1 = np.array(center1, dtype=float)
        self.center2 = np.array(center2, dtype=float)
        self.radius = float(radius)

    def _axis_angle(self) -> float:
        d = self.center2 - self.center1
        return math.atan2(float(d[1]), float(d[0]))

    def bounding_box(self):
        pts = self.to_points()
        return (float(pts[:, 0].min()), float(pts[:, 1].min()),
                float(pts[:, 0].max()), float(pts[:, 1].max()))

    def nearest_point(self, pt):
        pts = self.to_points()
        dists = np.linalg.norm(pts - pt, axis=1)
        return pts[int(np.argmin(dists))].copy()

    def translate(self, dx, dy):
        self.center1 += [dx, dy]
        self.center2 += [dx, dy]

    def rotate(self, angle_deg, origin):
        self.center1 = self._rotate_point(self.center1, angle_deg, origin)
        self.center2 = self._rotate_point(self.center2, angle_deg, origin)

    def scale(self, factor, origin):
        self.center1 = self._scale_point(self.center1, factor, origin)
        self.center2 = self._scale_point(self.center2, factor, origin)
        self.radius *= abs(factor)

    def to_dxf(self, msp):
        alpha = self._axis_angle()
        sa = math.degrees(alpha)
        # Left cap: start cap around center1 (facing away from center2)
        msp.add_arc(
            center=(float(self.center1[0]), float(self.center1[1]), 0),
            radius=self.radius,
            start_angle=(sa + 90) % 360,
            end_angle=(sa + 270) % 360,
            dxfattribs={"layer": self.layer},
        )
        # Right cap: end cap around center2
        msp.add_arc(
            center=(float(self.center2[0]), float(self.center2[1]), 0),
            radius=self.radius,
            start_angle=(sa - 90) % 360,
            end_angle=(sa + 90) % 360,
            dxfattribs={"layer": self.layer},
        )
        # Top and bottom lines
        perp = np.array([-math.sin(alpha), math.cos(alpha)]) * self.radius
        for sign in (1, -1):
            p1 = self.center1 + sign * perp
            p2 = self.center2 + sign * perp
            msp.add_line((float(p1[0]), float(p1[1]), 0),
                         (float(p2[0]), float(p2[1]), 0),
                         dxfattribs={"layer": self.layer})

    def to_points(self, n=64) -> np.ndarray:
        alpha = self._axis_angle()
        r = self.radius
        half = max(n // 4, 8)
        # Left cap: arc from α+90° → α+270° (CCW, facing away from center2)
        a1 = np.linspace(alpha + math.pi / 2, alpha + 3 * math.pi / 2, half)
        cap1 = self.center1 + r * np.column_stack([np.cos(a1), np.sin(a1)])
        # Right cap: arc from α-90° → α+90° (CCW, facing away from center1)
        a2 = np.linspace(alpha - math.pi / 2, alpha + math.pi / 2, half)
        cap2 = self.center2 + r * np.column_stack([np.cos(a2), np.sin(a2)])
        pts = np.vstack([cap1, cap2])
        return np.vstack([pts, pts[0]])    # closed

    def clone(self):
        e = GrooveEntity(self.center1.copy(), self.center2.copy(), self.radius)
        e.layer = self.layer
        e.color = self.color
        return e
