"""
ChandramaCAD – Selig DAT airfoil importer.
Reads a Selig-format .dat file and creates a PolylineEntity
scaled to the given chord length in mm.
"""
from __future__ import annotations
import numpy as np
from core.document import Document
from core.entities import PolylineEntity


def import_dat(path: str, chord_mm: float = 100.0) -> tuple[str, PolylineEntity]:
    """
    Parse a Selig airfoil .dat file and return (profile_name, PolylineEntity).
    The polyline is scaled so that chord = *chord_mm* mm.

    File format:
        ProfileName              ← first non-blank, non-comment line
        X1  Y1
        X2  Y2
        ...
    X/Y are normalised 0.0–1.0.  Upper surface is listed first (X from 1→0),
    then lower surface (X from 0→1), forming a closed loop.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()

    profile_name = "Airfoil"
    points_raw: list[tuple[float, float]] = []
    header_found = False

    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) == 1 and not header_found:
            profile_name = stripped
            header_found = True
            continue
        if len(parts) >= 2:
            try:
                x = float(parts[0])
                y = float(parts[1])
            except ValueError:
                if not header_found:
                    profile_name = stripped
                    header_found = True
                continue
            if not header_found:
                header_found = True  # first numeric line = implicit header was absent
            points_raw.append((x, y))

    if len(points_raw) < 4:
        raise ValueError(
            f"DAT file '{path}' has too few coordinate pairs ({len(points_raw)}).\n"
            "Expected at least 4 XY rows in Selig format."
        )

    arr = np.array(points_raw, dtype=float)

    # Normalise to 0..1 just in case the file is already in physical units
    x_range = arr[:, 0].max() - arr[:, 0].min()
    if x_range > 10.0:
        # Looks like physical units already — normalise
        chord_detected = x_range
        arr[:, 0] /= chord_detected
        arr[:, 1] /= chord_detected

    # Scale to chord_mm
    pts_mm = arr * chord_mm

    # Build polyline (open — leading and trailing edges typically share a point
    # already in the data, so we don't force-close)
    polyline_pts = [np.array([p[0], p[1]], dtype=float) for p in pts_mm]

    ent = PolylineEntity(polyline_pts, closed=False)
    return profile_name, ent


def import_dat_to_document(path: str, chord_mm: float = 100.0) -> Document:
    """
    Convenience wrapper: import a DAT file and return a fresh Document
    with the airfoil polyline on the Default layer.
    """
    from core.document import Document
    profile_name, ent = import_dat(path, chord_mm)
    doc = Document()
    ent.layer = "Default"
    doc.entities.append(ent)
    return doc
