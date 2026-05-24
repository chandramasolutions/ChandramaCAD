"""
Geometric intersection utilities used by Trim, Extend, Fillet, Chamfer and Offset.
All coordinates are 2-D numpy arrays in world (mm) space.
"""
from __future__ import annotations
import math
import numpy as np
from typing import Optional


# ── Low-level 2-D helpers ─────────────────────────────────────

def _cross2(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def line_line_intersect(p1: np.ndarray, p2: np.ndarray,
                        p3: np.ndarray, p4: np.ndarray
                        ) -> Optional[tuple[float, float, np.ndarray]]:
    """
    Infinite-line intersection of (p1→p2) with (p3→p4).
    Returns (t, u, point) where point = p1 + t*(p2-p1).
    t=0 is p1, t=1 is p2 (same for u along p3-p4).
    Returns None if lines are parallel / coincident.
    """
    d1 = p2 - p1
    d2 = p4 - p3
    denom = _cross2(d1, d2)
    if abs(denom) < 1e-10:
        return None
    dp = p3 - p1
    t = _cross2(dp, d2) / denom
    u = _cross2(dp, d1) / denom
    return t, u, p1 + t * d1


def seg_seg_intersect(p1: np.ndarray, p2: np.ndarray,
                      p3: np.ndarray, p4: np.ndarray
                      ) -> Optional[tuple[float, float, np.ndarray]]:
    """
    Segment-segment intersection.  Same return as line_line_intersect,
    but also checks 0 ≤ t ≤ 1 and 0 ≤ u ≤ 1.
    """
    result = line_line_intersect(p1, p2, p3, p4)
    if result is None:
        return None
    t, u, pt = result
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t, u, pt
    return None


def circle_line_t(center: np.ndarray, radius: float,
                  p1: np.ndarray, p2: np.ndarray) -> list[tuple[float, np.ndarray]]:
    """
    Returns list of (t, point) where infinite line p1+t*(p2-p1) hits the circle.
    """
    d = p2 - p1
    f = p1 - center
    a = float(np.dot(d, d))
    b = 2.0 * float(np.dot(f, d))
    c = float(np.dot(f, f)) - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < 0.0 or a < 1e-12:
        return []
    sq = math.sqrt(max(0.0, disc))
    out = []
    for sign in (-1.0, 1.0):
        t = (-b + sign * sq) / (2.0 * a)
        out.append((t, p1 + t * d))
    return out


# ── Mirror ────────────────────────────────────────────────────

def mirror_point(pt: np.ndarray,
                 axis_p1: np.ndarray, axis_p2: np.ndarray) -> np.ndarray:
    """Reflect pt across the infinite line through axis_p1 and axis_p2."""
    d = axis_p2 - axis_p1
    dl = float(np.dot(d, d))
    if dl < 1e-12:
        return pt.copy()
    t = float(np.dot(pt - axis_p1, d)) / dl
    foot = axis_p1 + t * d
    return 2.0 * foot - pt


# ── Offset ────────────────────────────────────────────────────

def offset_segment(p1: np.ndarray, p2: np.ndarray,
                   dist: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns the two endpoints of p1-p2 offset perpendicularly by dist
    (positive dist = left side when travelling p1→p2).
    """
    d = p2 - p1
    length = float(np.linalg.norm(d))
    if length < 1e-12:
        return p1.copy(), p2.copy()
    perp = np.array([-d[1], d[0]]) / length * dist
    return p1 + perp, p2 + perp


def offset_polyline(points: list[np.ndarray], dist: float,
                    closed: bool = False) -> list[np.ndarray]:
    """
    Offset a polyline by *dist* mm (positive = left of travel direction).
    Corner junctions are resolved by intersecting adjacent offset segments.
    Returns a new list of offset points.
    """
    n = len(points)
    if n < 2:
        return [p.copy() for p in points]

    pts = list(points)
    if closed:
        pts = pts + [pts[0]]

    # Build offset segments
    segs: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(len(pts) - 1):
        segs.append(offset_segment(pts[i], pts[i + 1], dist))

    if not segs:
        return [p.copy() for p in points]

    result: list[np.ndarray] = [segs[0][0]]
    for i in range(len(segs) - 1):
        s1p1, s1p2 = segs[i]
        s2p1, s2p2 = segs[i + 1]
        inter = line_line_intersect(s1p1, s1p2, s2p1, s2p2)
        if inter is not None:
            result.append(inter[2])
        else:
            result.append(s1p2)
    result.append(segs[-1][1])
    return result


# ── Trim helpers ──────────────────────────────────────────────

def t_values_on_line(p1: np.ndarray, p2: np.ndarray,
                     entities, exclude_id: int) -> list[float]:
    """
    Find all parametric t values (along p1→p2) where the line segment
    is intersected by other entities (lines or circles).  Only returns
    t values in [0, 1] where the boundary entity is also hit within its
    own extent.
    """
    ts: list[float] = []
    from core.entities import LineEntity, CircleEntity, ArcEntity  # local import avoids cycle

    for other in entities:
        if other.id == exclude_id:
            continue
        if isinstance(other, LineEntity):
            res = line_line_intersect(p1, p2, other.start, other.end)
            if res:
                t, u, _ = res
                if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                    ts.append(t)
        elif isinstance(other, CircleEntity):
            for t, _ in circle_line_t(other.center, other.radius, p1, p2):
                if 0.0 <= t <= 1.0:
                    ts.append(t)
        elif isinstance(other, ArcEntity):
            for t, pt in circle_line_t(other.center, other.radius, p1, p2):
                if 0.0 <= t <= 1.0:
                    # Check if pt lies within the arc's angle span
                    angle = math.degrees(math.atan2(
                        float(pt[1] - other.center[1]),
                        float(pt[0] - other.center[0]))) % 360
                    sa = other.start_angle % 360
                    span = other._angle_span()
                    rel = (angle - sa) % 360
                    if rel <= span:
                        ts.append(t)
    ts.sort()
    return ts


# ── Fillet ────────────────────────────────────────────────────

def fillet_lines(p1: np.ndarray, p2: np.ndarray,
                 p3: np.ndarray, p4: np.ndarray,
                 radius: float
                 ) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray,
                                     float, float, np.ndarray]]:
    """
    Compute a circular fillet of given radius between lines (p1→p2) and (p3→p4).
    Returns (trim_pt1, trim_pt2, arc_center, arc_start_deg, arc_end_deg, corner)
    or None if fillet is not possible.
    trim_pt1 is where line 1 should be trimmed to; trim_pt2 for line 2.
    """
    inter = line_line_intersect(p1, p2, p3, p4)
    if inter is None:
        return None
    _t, _u, corner = inter

    d1 = p2 - p1
    d2 = p4 - p3
    l1 = float(np.linalg.norm(d1))
    l2 = float(np.linalg.norm(d2))
    if l1 < 1e-10 or l2 < 1e-10:
        return None

    u1 = d1 / l1   # unit vector of line 1
    u2 = d2 / l2   # unit vector of line 2

    # Half-angle bisector
    cos_half = float(np.dot(u1, u2))
    cos_half = max(-1.0, min(1.0, cos_half))
    half_angle = math.acos(cos_half) / 2.0
    if abs(math.sin(half_angle)) < 1e-10:
        return None

    # Distance from corner to tangent point along each line
    d = radius / math.tan(half_angle)

    # Tangent points (clamp to line length as sanity check)
    tp1 = corner - u1 * d   # on line 1 (going backward from corner)
    tp2 = corner - u2 * d   # on line 2 (going backward from corner)

    # Arc centre: move from corner along bisector
    bisector = (u1 + u2)
    b_len = float(np.linalg.norm(bisector))
    if b_len < 1e-10:
        return None
    bisector /= b_len
    arc_center = corner - bisector * (radius / math.sin(half_angle))

    # Arc angles
    def ang(v): return math.degrees(math.atan2(float(v[1]), float(v[0]))) % 360

    sa = ang(tp1 - arc_center)
    ea = ang(tp2 - arc_center)

    return tp1, tp2, arc_center, sa, ea, corner


# ── Chamfer ───────────────────────────────────────────────────

def chamfer_lines(p1: np.ndarray, p2: np.ndarray,
                  p3: np.ndarray, p4: np.ndarray,
                  d1: float, d2: float
                  ) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """
    Compute a chamfer between line (p1→p2) and (p3→p4).
    d1 = trim distance along line 1 from corner; d2 along line 2.
    Returns (trim_pt1, trim_pt2, corner) or None.
    """
    inter = line_line_intersect(p1, p2, p3, p4)
    if inter is None:
        return None
    _t, _u, corner = inter
    dir1 = p2 - p1
    dir2 = p4 - p3
    l1 = float(np.linalg.norm(dir1))
    l2 = float(np.linalg.norm(dir2))
    if l1 < 1e-10 or l2 < 1e-10:
        return None
    tp1 = corner - (dir1 / l1) * d1
    tp2 = corner - (dir2 / l2) * d2
    return tp1, tp2, corner
