from __future__ import annotations
import ezdxf
import numpy as np
from core.document import Document
from core.entities import Entity


def export_dxf(document: Document, path: str):
    """Export all visible entities to a DXF R2010 file."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Create DXF layers
    for layer in document.layers:
        if layer.name not in doc.layers:
            dxf_layer = doc.layers.new(layer.name)
            # Convert hex color to ACI index (approximate)
            dxf_layer.color = 7  # default white/black

    for entity in document.visible_entities():
        try:
            entity.to_dxf(msp)
        except Exception:
            pass  # skip entities that fail DXF export

    doc.saveas(path)


def export_dat(document: Document, path: str, profile_name: str = "Profile"):
    """
    Export selected closed polyline/spline as Selig airfoil DAT.
    Points are written as 'X Y' pairs, normalised 0.0–1.0.
    If nothing is selected, exports all visible polylines / splines.
    """
    selected = document.selected_entities()
    if not selected:
        selected = document.visible_entities()

    # Find first polyline or spline
    target_entity = None
    for e in selected:
        from core.entities import PolylineEntity, SplineEntity
        if isinstance(e, (PolylineEntity, SplineEntity)):
            target_entity = e
            break

    if target_entity is None:
        raise ValueError("No polyline or spline found for DAT export. "
                         "Select a closed polyline or spline first.")

    pts = target_entity.to_points(n=200)

    # Normalise to 0..1
    xs, ys = pts[:, 0], pts[:, 1]
    x_range = xs.max() - xs.min()
    y_range = ys.max() - ys.min()
    scale = max(x_range, y_range)
    if scale < 1e-12:
        scale = 1.0
    xs_norm = (xs - xs.min()) / scale
    ys_norm = (ys - ys.min()) / scale

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{profile_name}\n")
        for x, y in zip(xs_norm, ys_norm):
            f.write(f"{x:.6f}  {y:.6f}\n")
