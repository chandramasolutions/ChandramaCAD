from __future__ import annotations
import math
import numpy as np
from typing import Optional
from core.entities import (
    Entity, LineEntity, PolylineEntity, RectangleEntity,
    CircleEntity, ArcEntity, SplineEntity,
)


class SnapResult:
    def __init__(self, point: np.ndarray, snap_type: str):
        self.point = np.array(point, dtype=float)
        self.snap_type = snap_type  # "grid" | "endpoint" | "midpoint" | "center" | "none"


class SnapEngine:
    def __init__(self):
        self.grid_snap_enabled: bool = True
        self.endpoint_snap_enabled: bool = True
        self.midpoint_snap_enabled: bool = True
        self.center_snap_enabled: bool = True
        self.grid_size: float = 1.0   # mm
        self.snap_radius_px: float = 12.0  # screen pixels

    def snap(self, world_pt: np.ndarray, entities: list[Entity],
             scale: float) -> SnapResult:
        """Return best snap point for world_pt given current entities and zoom scale."""
        snap_radius_world = self.snap_radius_px / scale

        best: Optional[SnapResult] = None
        best_dist = float("inf")

        # 1. Endpoint snap
        if self.endpoint_snap_enabled:
            for e in entities:
                candidates = self._endpoint_candidates(e)
                for c in candidates:
                    d = float(np.linalg.norm(world_pt - c))
                    if d < snap_radius_world and d < best_dist:
                        best_dist = d
                        best = SnapResult(c, "endpoint")

        # 2. Midpoint snap
        if self.midpoint_snap_enabled:
            for e in entities:
                candidates = self._midpoint_candidates(e)
                for c in candidates:
                    d = float(np.linalg.norm(world_pt - c))
                    if d < snap_radius_world and d < best_dist:
                        best_dist = d
                        best = SnapResult(c, "midpoint")

        # 3. Center snap
        if self.center_snap_enabled:
            for e in entities:
                c = self._center_candidate(e)
                if c is not None:
                    d = float(np.linalg.norm(world_pt - c))
                    if d < snap_radius_world and d < best_dist:
                        best_dist = d
                        best = SnapResult(c, "center")

        if best is not None:
            return best

        # 4. Grid snap (fallback)
        if self.grid_snap_enabled:
            gs = self.grid_size
            snapped = np.round(world_pt / gs) * gs
            return SnapResult(snapped, "grid")

        return SnapResult(world_pt, "none")

    def _endpoint_candidates(self, e: Entity) -> list[np.ndarray]:
        if isinstance(e, LineEntity):
            return [e.start.copy(), e.end.copy()]
        if isinstance(e, PolylineEntity) and e.points:
            pts = [e.points[0].copy(), e.points[-1].copy()]
            return pts
        if isinstance(e, RectangleEntity):
            return [c.copy() for c in e._corners]
        if isinstance(e, (CircleEntity, ArcEntity)):
            return []  # circles have no start/end in the usual sense
        if isinstance(e, SplineEntity) and e.control_points:
            return [e.control_points[0].copy(), e.control_points[-1].copy()]
        return []

    def _midpoint_candidates(self, e: Entity) -> list[np.ndarray]:
        if isinstance(e, LineEntity):
            return [(e.start + e.end) / 2]
        if isinstance(e, PolylineEntity):
            mids = []
            pts = e.points
            for i in range(len(pts) - 1):
                mids.append((pts[i] + pts[i + 1]) / 2)
            return mids
        if isinstance(e, RectangleEntity):
            corners = e._corners
            mids = []
            for i in range(4):
                mids.append((corners[i] + corners[(i + 1) % 4]) / 2)
            return mids
        return []

    def _center_candidate(self, e: Entity) -> Optional[np.ndarray]:
        if isinstance(e, CircleEntity):
            return e.center.copy()
        if isinstance(e, ArcEntity):
            return e.center.copy()
        if isinstance(e, RectangleEntity):
            return (e.corner1 + e.corner2) / 2
        return None
