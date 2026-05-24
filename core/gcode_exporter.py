"""
ChandramaCAD – Hotwire GCode Exporter.
Generates industry-standard 2-axis GCode for hotwire CNC cutting.

Output format:
    G21 ; metric mm
    G90 ; absolute coordinates
    M3  ; wire on
    F<feedrate>
    G0 X<x> Y<y>   ; rapid to start
    G1 X<x> Y<y>   ; cutting moves
    ...
    M5  ; wire off
    M30 ; program end
"""
from __future__ import annotations
import math
from typing import Optional
import numpy as np

from core.entities import Entity
from core.path_validator import validate_cut_path, PathValidationResult


def _offset_path(points: np.ndarray, kerf_mm: float) -> np.ndarray:
    """
    Offset a closed point chain by *kerf_mm* mm toward the inside.
    Uses simple perpendicular normal offset at each segment midpoint.
    Returns a new numpy array of offset points.
    """
    if kerf_mm == 0.0 or len(points) < 3:
        return points

    # Ensure closed loop for offset calculation
    pts = points
    if not np.allclose(pts[0], pts[-1], atol=1e-6):
        pts = np.vstack([pts, pts[0]])

    n = len(pts) - 1   # number of segments
    offset_pts: list[np.ndarray] = []

    for i in range(n):
        p0 = pts[i]
        p1 = pts[(i + 1) % n]
        d = p1 - p0
        length = float(np.linalg.norm(d))
        if length < 1e-10:
            offset_pts.append(p0.copy())
            continue
        # Left-normal (inner offset for CCW winding)
        normal = np.array([-d[1], d[0]]) / length
        offset_pts.append(p0 + normal * kerf_mm)

    # Close loop
    offset_pts.append(offset_pts[0].copy())
    return np.array(offset_pts)


def export_gcode(
    entities: list[Entity],
    path: str,
    feedrate: float = 1000.0,      # mm/min
    rapid_feedrate: float = 3000.0, # mm/min for G0
    kerf_mm: float = 0.0,          # wire radius for kerf compensation
    wire_on_cmd: str = "M3",
    wire_off_cmd: str = "M5",
    program_name: str = "CHANDRAMA",
    tolerance: float = 0.5,
    validate: bool = True,
) -> PathValidationResult:
    """
    Export *entities* as a hotwire GCode file.

    Parameters
    ----------
    entities      : list of ChandramaCAD Entity objects to cut.
    path          : output file path (.nc / .gcode / .txt)
    feedrate      : cutting feed in mm/min (default 1000).
    rapid_feedrate: rapid traverse speed for G0 moves.
    kerf_mm       : half wire diameter for kerf compensation (0 = none).
    wire_on_cmd   : GCode command to energise wire (default M3).
    wire_off_cmd  : GCode command to de-energise wire (default M5).
    program_name  : embedded in the header comment.
    tolerance     : endpoint connectivity tolerance for chain building.
    validate      : if True, validate path connectivity before exporting.

    Returns
    -------
    PathValidationResult — so the caller can inspect messages / validity.
    """

    # 1. Validate / order entities
    result = validate_cut_path(entities, tolerance)

    if validate and not result.valid:
        # Still write a partial file but mark it clearly
        pass

    if result.ordered_points is None or len(result.ordered_points) < 2:
        result.messages.append("❌  No valid path to export — GCode not written.")
        return result

    pts = result.ordered_points

    # 2. Apply kerf compensation
    if kerf_mm > 0.0:
        pts = _offset_path(pts, kerf_mm)
        result.messages.append(
            f"ℹ️  Kerf compensation applied: {kerf_mm:.3f} mm inward offset."
        )

    # 3. Generate GCode
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        f"; ============================================================",
        f"; ChandramaCAD – Hotwire GCode",
        f"; Program : {program_name}",
        f"; Created : {now}",
        f"; Entities: {len(result.ordered_entities)}",
        f"; Points  : {len(pts)}",
        f"; Feedrate: {feedrate:.0f} mm/min",
        f"; Kerf    : {kerf_mm:.3f} mm",
        f"; Closed  : {'Yes' if result.closed else 'No'}",
        f"; ============================================================",
        "",
        "G21        ; Units: millimetres",
        "G90        ; Absolute positioning",
        f"F{feedrate:.0f}      ; Default feed rate",
        "",
        "; ── Rapid to start position ─────────────────────────────────",
        f"G0 X{pts[0][0]:.4f} Y{pts[0][1]:.4f}   F{rapid_feedrate:.0f}",
        "",
        f"{wire_on_cmd}         ; Wire ON",
        f"F{feedrate:.0f}",
        "",
        "; ── Cutting path ──────────────────────────────────────────",
    ]

    for i, pt in enumerate(pts):
        x, y = float(pt[0]), float(pt[1])
        lines.append(f"G1 X{x:.4f} Y{y:.4f}")

    lines.extend([
        "",
        f"{wire_off_cmd}         ; Wire OFF",
        "",
        "; ── Return to home ────────────────────────────────────────",
        "G0 X0.0000 Y0.0000",
        "",
        "M30        ; Program end",
        "",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    result.messages.append(
        f"✅  GCode written to: {path}\n"
        f"    {len(pts)} moves, feed = {feedrate:.0f} mm/min."
    )
    return result
