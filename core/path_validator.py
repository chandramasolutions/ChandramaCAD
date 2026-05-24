"""
ChandramaCAD – Cut-path validator for hotwire CNC.
Checks whether a set of entities form a single, closed, continuous chain
suitable for hotwire cutting.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from core.entities import (
    Entity, LineEntity, PolylineEntity, ArcEntity, CircleEntity,
    SplineEntity, RectangleEntity, PolygonEntity, EllipseEntity,
    SemiCircleEntity, GrooveEntity,
)


_CONNECT_TOL: float = 0.5   # mm — endpoints must be within this distance to be "connected"


@dataclass
class PathValidationResult:
    valid: bool
    closed: bool
    messages: list[str] = field(default_factory=list)
    ordered_entities: list[Entity] = field(default_factory=list)
    ordered_points: Optional[np.ndarray] = None   # flattened point chain
    open_start: Optional[np.ndarray] = None        # first open endpoint
    open_end: Optional[np.ndarray] = None          # last open endpoint


def _endpoints(entity: Entity) -> tuple[np.ndarray, np.ndarray]:
    """Return the (start, end) endpoints of an entity."""
    if isinstance(entity, LineEntity):
        return entity.start.copy(), entity.end.copy()
    if isinstance(entity, PolylineEntity) and entity.points:
        return entity.points[0].copy(), entity.points[-1].copy()
    if isinstance(entity, ArcEntity):
        sa_rad = math.radians(entity.start_angle)
        ea_rad = math.radians(entity.start_angle + entity._angle_span())
        start = entity.center + entity.radius * np.array([math.cos(sa_rad), math.sin(sa_rad)])
        end   = entity.center + entity.radius * np.array([math.cos(ea_rad), math.sin(ea_rad)])
        return start, end
    if isinstance(entity, SplineEntity) and entity.control_points:
        return entity.control_points[0].copy(), entity.control_points[-1].copy()
    if isinstance(entity, (RectangleEntity, PolygonEntity,
                           EllipseEntity, SemiCircleEntity, GrooveEntity)):
        pts = entity.to_points()
        return pts[0].copy(), pts[-1].copy()
    if isinstance(entity, CircleEntity):
        # Full circle: both endpoints are the same (closed curve)
        ep = entity.center + np.array([entity.radius, 0.0])
        return ep.copy(), ep.copy()
    raise ValueError(f"Cannot extract endpoints for {type(entity).__name__}")


def _points_chain(entity: Entity, reversed_: bool = False) -> np.ndarray:
    """Return ordered sample points for an entity (optionally reversed)."""
    if isinstance(entity, LineEntity):
        pts = np.array([entity.start, entity.end])
    elif isinstance(entity, PolylineEntity):
        pts = np.array(entity.points)
    elif isinstance(entity, ArcEntity):
        pts = entity.to_points(64)
    elif isinstance(entity, SplineEntity):
        pts = entity.to_points(200)
    elif isinstance(entity, CircleEntity):
        pts = entity.to_points(200)
    else:
        pts = entity.to_points()

    if reversed_:
        pts = pts[::-1]
    return pts


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def validate_cut_path(
    entities: list[Entity],
    tolerance: float = _CONNECT_TOL,
) -> PathValidationResult:
    """
    Validate that *entities* form a single continuous (ideally closed) chain.

    Returns a PathValidationResult with:
    - ``valid``            – True if entities form a single chain (open or closed)
    - ``closed``           – True if the chain is closed (last connects to first)
    - ``messages``         – Human-readable list of issues found
    - ``ordered_entities`` – Entities sorted in chain order
    - ``ordered_points``   – Concatenated points of the full path
    - ``open_start`` / ``open_end`` – World-coord endpoints if path is open
    """
    result = PathValidationResult(valid=False, closed=False)

    # Filter to cuttable geometry only (exclude annotation entities)
    from core.entities import PointEntity, TextEntity, DimLinearEntity, DimRadialEntity
    cuttable = [e for e in entities
                if not isinstance(e, (PointEntity, TextEntity,
                                      DimLinearEntity, DimRadialEntity))]

    if not cuttable:
        result.messages.append("❌  No cuttable geometry found in selection.")
        return result

    if len(cuttable) == 1:
        e = cuttable[0]
        try:
            s, en = _endpoints(e)
            closed = _dist(s, en) <= tolerance
            chain_pts = _points_chain(e)
            result.valid = True
            result.closed = closed
            result.ordered_entities = [e]
            result.ordered_points = chain_pts
            if closed:
                result.messages.append("✅  Single closed entity — ready for cutting.")
            else:
                result.open_start = s
                result.open_end = en
                result.messages.append(
                    f"⚠️  Single open entity — gap = {_dist(s, en):.3f} mm.")
        except Exception as exc:
            result.messages.append(f"❌  Cannot process entity: {exc}")
        return result

    # ── Greedy chain-building ─────────────────────────────────────────────────
    remaining = list(cuttable)
    chain: list[Entity] = [remaining.pop(0)]
    reversed_flags: list[bool] = [False]

    # Cached endpoints
    def ep(e: Entity) -> tuple[np.ndarray, np.ndarray]:
        return _endpoints(e)

    current_end = ep(chain[0])[1]

    max_iterations = len(cuttable) * 2
    for _ in range(max_iterations):
        if not remaining:
            break
        best_idx, best_dist_, best_rev = -1, float("inf"), False
        for idx, candidate in enumerate(remaining):
            try:
                s, en = ep(candidate)
            except Exception:
                continue
            d_fwd = _dist(current_end, s)
            d_rev = _dist(current_end, en)
            if d_fwd < best_dist_:
                best_dist_, best_idx, best_rev = d_fwd, idx, False
            if d_rev < best_dist_:
                best_dist_, best_idx, best_rev = d_rev, idx, True

        if best_idx < 0 or best_dist_ > tolerance:
            break   # disconnected — no candidate close enough

        next_e = remaining.pop(best_idx)
        chain.append(next_e)
        reversed_flags.append(best_rev)
        current_end = ep(next_e)[1 if not best_rev else 0]

    # ── Build result ──────────────────────────────────────────────────────────
    result.ordered_entities = chain

    if remaining:
        result.messages.append(
            f"❌  Path is disconnected — {len(remaining)} entity(ies) not connected:\n"
            + "\n".join(f"   • {type(e).__name__} (id={e.id})" for e in remaining)
        )
        result.valid = False
    else:
        result.valid = True

    # Concatenate points
    all_pts: list[np.ndarray] = []
    for e, rev in zip(chain, reversed_flags):
        pts = _points_chain(e, rev)
        if all_pts:
            all_pts.append(pts)  # avoid duplicate junction points by skipping first point
        else:
            all_pts.append(pts)
    if all_pts:
        result.ordered_points = np.vstack(all_pts)

    # Check closure
    chain_start = ep(chain[0])[0 if not reversed_flags[0] else 1]
    chain_end = current_end
    gap = _dist(chain_start, chain_end)
    result.closed = gap <= tolerance

    if result.valid and result.closed:
        result.messages.append(
            f"✅  Closed path with {len(chain)} entity(ies) — ready for GCode export."
        )
    elif result.valid and not result.closed:
        result.open_start = chain_start
        result.open_end = chain_end
        result.messages.append(
            f"⚠️  Open path with {len(chain)} entity(ies). "
            f"Gap between start and end = {gap:.3f} mm."
        )

    return result
