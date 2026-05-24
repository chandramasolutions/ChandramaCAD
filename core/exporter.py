"""
ChandramaCAD – Export pipeline.
Supports: DXF (R2010), DAT (Selig airfoil), SVG, PDF.
"""
from __future__ import annotations
import math
import os
from typing import Optional

import numpy as np

from core.document import Document
from core.entities import (
    Entity, LineEntity, PolylineEntity, RectangleEntity,
    CircleEntity, ArcEntity, SplineEntity,
    PolygonEntity, EllipseEntity, SemiCircleEntity, GrooveEntity,
    PointEntity, TextEntity, DimLinearEntity, DimRadialEntity,
)
from core.color_utils import (
    hex_to_aci, hex_to_rgb_int, hex_to_rgb, aci_to_hex,
    LINETYPE_DXF_PATTERNS, LINETYPE_SVG_DASH,
)


# ── DXF Export ───────────────────────────────────────────────────────────────

def _setup_dxf_linetypes(doc) -> None:
    """Register all custom linetypes into the ezdxf document linetype table."""
    ltype_table = doc.linetypes
    for name, (desc, pattern_len, elements) in LINETYPE_DXF_PATTERNS.items():
        if name not in ltype_table:
            try:
                ltype_table.new(
                    name,
                    dxfattribs={
                        "description": desc,
                        "pattern_length": pattern_len,
                        "pattern": elements,
                    },
                )
            except Exception:
                pass  # already exists or not supported


def export_dxf(document: Document, path: str) -> None:
    """Export all visible entities to a DXF R2010 file with correct colours and linetypes."""
    import ezdxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # ── Header variables ─────────────────────────────────
    # $INSUNITS = 4 → millimetres; $MEASUREMENT = 1 → metric
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LUNITS"] = 2       # decimal units
    doc.header["$LUPREC"] = 4       # 4 decimal places

    # ── Register linetypes ───────────────────────────────
    _setup_dxf_linetypes(doc)

    # ── Create DXF layers ────────────────────────────────
    for layer in document.layers:
        if layer.name not in doc.layers:
            dxf_layer = doc.layers.new(layer.name)
        else:
            dxf_layer = doc.layers.get(layer.name)

        # Set colour
        try:
            aci = hex_to_aci(layer.color)
            dxf_layer.color = aci
            # true_color for R2004+ compatibility
            r, g, b = hex_to_rgb(layer.color)
            dxf_layer.true_color = (r << 16) | (g << 8) | b
        except Exception:
            dxf_layer.color = 7

        # Set linetype
        lt = layer.linetype if layer.linetype else "CONTINUOUS"
        if lt != "CONTINUOUS" and lt in LINETYPE_DXF_PATTERNS:
            try:
                dxf_layer.linetype = lt
            except Exception:
                pass

        # Visibility (DXF freeze = invisible)
        if not layer.visible:
            try:
                dxf_layer.is_frozen = True
            except Exception:
                pass

    # ── Export entities ──────────────────────────────────
    for entity in document.visible_entities():
        try:
            entity.to_dxf(msp)
        except Exception:
            pass   # skip entities that fail DXF export

    doc.saveas(path)


# ── DAT Export (Selig airfoil) ────────────────────────────────────────────────

def export_dat(document: Document, path: str, profile_name: str = "Profile",
               chord_mm: float = 100.0) -> None:
    """
    Export the selected (or first visible) closed polyline/spline as Selig
    airfoil DAT format.  The chord axis is auto-detected as the major axis.
    Points are written normalised to 0.0–1.0 chord fraction.
    """
    selected = document.selected_entities()
    if not selected:
        selected = document.visible_entities()

    target = None
    for e in selected:
        if isinstance(e, (PolylineEntity, SplineEntity)):
            target = e
            break

    if target is None:
        raise ValueError(
            "No polyline or spline found for DAT export.\n"
            "Select a closed polyline or spline first."
        )

    pts = target.to_points(n=200)
    if len(pts) < 3:
        raise ValueError("Profile has too few points for DAT export.")

    xs, ys = pts[:, 0], pts[:, 1]

    # Normalise: x direction is chord (max extent), y is thickness
    x_range = xs.max() - xs.min()
    y_range = ys.max() - ys.min()
    chord = max(x_range, y_range)
    if chord < 1e-6:
        raise ValueError("Profile bounding box is too small to normalise.")

    # Orient so that leading edge is at x=0, trailing edge at x=1
    xs_n = (xs - xs.min()) / chord
    ys_n = (ys - ys.min()) / chord

    profile_name = profile_name or os.path.splitext(os.path.basename(path))[0]

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{profile_name}\n")
        for x, y in zip(xs_n, ys_n):
            f.write(f"  {x:.6f}  {y:.6f}\n")


# ── SVG Export ────────────────────────────────────────────────────────────────

def _entity_svg(entity: Entity, layer_color: str,
                y_max: float, margin: float = 10.0) -> list[str]:
    """
    Return a list of SVG element strings for the given entity.
    Y is flipped: svg_y = (y_max + margin) - world_y
    """
    def fy(wy: float) -> float:
        return (y_max + margin) - wy

    def hex_color(e: Entity) -> str:
        return e.color if e.color else layer_color

    def stroke_dasharray(lt: str) -> str:
        return LINETYPE_SVG_DASH.get(lt, "none")

    def base_style(e: Entity, stroke_w: float = 0.5) -> str:
        color = hex_color(e)
        dash = stroke_dasharray(getattr(e, "linetype", "CONTINUOUS"))
        s = f'stroke="{color}" stroke-width="{stroke_w}" fill="none"'
        if dash != "none":
            s += f' stroke-dasharray="{dash}"'
        return s

    lines: list[str] = []

    if isinstance(entity, LineEntity):
        x1, y1 = float(entity.start[0]) + margin, fy(float(entity.start[1]))
        x2, y2 = float(entity.end[0]) + margin,   fy(float(entity.end[1]))
        lines.append(f'  <line x1="{x1:.4f}" y1="{y1:.4f}" '
                     f'x2="{x2:.4f}" y2="{y2:.4f}" {base_style(entity)}/>')

    elif isinstance(entity, (PolylineEntity, RectangleEntity, PolygonEntity)):
        pts = entity.to_points()
        coords = " ".join(f"{p[0] + margin:.4f},{fy(p[1]):.4f}" for p in pts)
        closed = getattr(entity, "closed", False) or isinstance(entity, (RectangleEntity, PolygonEntity))
        tag = "polygon" if closed else "polyline"
        lines.append(f'  <{tag} points="{coords}" {base_style(entity)}/>')

    elif isinstance(entity, CircleEntity):
        cx = float(entity.center[0]) + margin
        cy = fy(float(entity.center[1]))
        lines.append(f'  <circle cx="{cx:.4f}" cy="{cy:.4f}" '
                     f'r="{entity.radius:.4f}" {base_style(entity)}/>')

    elif isinstance(entity, ArcEntity):
        sa_rad = math.radians(entity.start_angle)
        ea_rad = math.radians(entity.start_angle + entity._angle_span())
        cx, cy_w = float(entity.center[0]), float(entity.center[1])
        r = entity.radius
        # SVG arc: Y-flipped → angles flip sign
        x1 = cx + r * math.cos(sa_rad) + margin
        y1 = fy(cy_w + r * math.sin(sa_rad))
        x2 = cx + r * math.cos(ea_rad) + margin
        y2 = fy(cy_w + r * math.sin(ea_rad))
        span = entity._angle_span()
        large = 1 if span > 180 else 0
        # Sweep = 0 because Y is flipped (clockwise in SVG = CCW in world)
        lines.append(f'  <path d="M {x1:.4f},{y1:.4f} '
                     f'A {r:.4f},{r:.4f} 0 {large},0 {x2:.4f},{y2:.4f}" '
                     f'{base_style(entity)}/>')

    elif isinstance(entity, EllipseEntity):
        pts = entity.to_points(128)
        coords = " ".join(f"{p[0] + margin:.4f},{fy(p[1]):.4f}" for p in pts)
        lines.append(f'  <polygon points="{coords}" {base_style(entity)}/>')

    elif isinstance(entity, SplineEntity):
        pts = entity.to_points(200)
        if len(pts) >= 2:
            coords = " ".join(f"{p[0] + margin:.4f},{fy(p[1]):.4f}" for p in pts)
            lines.append(f'  <polyline points="{coords}" {base_style(entity)}/>')

    elif isinstance(entity, (SemiCircleEntity, GrooveEntity)):
        pts = entity.to_points(64)
        coords = " ".join(f"{p[0] + margin:.4f},{fy(p[1]):.4f}" for p in pts)
        lines.append(f'  <polygon points="{coords}" {base_style(entity)}/>')

    elif isinstance(entity, PointEntity):
        cx = float(entity.position[0]) + margin
        cy = fy(float(entity.position[1]))
        color = hex_color(entity)
        lines.append(f'  <circle cx="{cx:.4f}" cy="{cy:.4f}" '
                     f'r="1" stroke="{color}" stroke-width="0.5" fill="{color}"/>')

    elif isinstance(entity, TextEntity):
        tx = float(entity.position[0]) + margin
        ty = fy(float(entity.position[1]))
        color = hex_color(entity)
        rot = -entity.rotation_deg  # SVG text rotation is CW
        lines.append(f'  <text x="{tx:.4f}" y="{ty:.4f}" '
                     f'font-size="{entity.height:.4f}" fill="{color}" '
                     f'transform="rotate({rot:.2f},{tx:.4f},{ty:.4f})">'
                     f'{entity.text}</text>')

    elif isinstance(entity, DimLinearEntity):
        # Draw as simple leader line + measurement text
        mid = (entity.p1 + entity.p2) / 2
        off_vec = np.array([0.0, entity.offset])
        p_dim = mid + off_vec
        x1 = float(entity.p1[0]) + margin
        y1_s = fy(float(entity.p1[1]))
        x2 = float(entity.p2[0]) + margin
        y2_s = fy(float(entity.p2[1]))
        xd = float(p_dim[0]) + margin
        yd = fy(float(p_dim[1]))
        meas = f"{entity.measurement():.2f}"
        color = hex_color(entity)
        lines.append(f'  <line x1="{x1:.3f}" y1="{y1_s:.3f}" x2="{x2:.3f}" y2="{y2_s:.3f}" '
                     f'stroke="{color}" stroke-width="0.3" stroke-dasharray="2,1"/>')
        lines.append(f'  <text x="{xd:.3f}" y="{yd:.3f}" font-size="3.5" fill="{color}">'
                     f'{meas}</text>')

    elif isinstance(entity, DimRadialEntity):
        angle_rad = math.radians(entity.angle_deg)
        tip = entity.center + entity.radius * np.array([math.cos(angle_rad), math.sin(angle_rad)])
        cx = float(entity.center[0]) + margin
        cy_s = fy(float(entity.center[1]))
        tx = float(tip[0]) + margin
        ty_s = fy(float(tip[1]))
        prefix = "⌀" if entity.is_diameter else "R"
        val = entity.radius * (2 if entity.is_diameter else 1)
        color = hex_color(entity)
        lines.append(f'  <line x1="{cx:.3f}" y1="{cy_s:.3f}" x2="{tx:.3f}" y2="{ty_s:.3f}" '
                     f'stroke="{color}" stroke-width="0.3"/>')
        lines.append(f'  <text x="{tx:.3f}" y="{ty_s:.3f}" font-size="3.5" fill="{color}">'
                     f'{prefix}{val:.2f}</text>')

    return lines


def export_svg(document: Document, path: str, margin_mm: float = 10.0) -> None:
    """Export all visible entities to an SVG file in mm coordinates."""
    entities = document.visible_entities()
    if not entities:
        raise ValueError("No visible entities to export.")

    # Build bounding box
    all_bb = [e.bounding_box() for e in entities]
    min_x = min(bb[0] for bb in all_bb)
    min_y = min(bb[1] for bb in all_bb)
    max_x = max(bb[2] for bb in all_bb)
    max_y = max(bb[3] for bb in all_bb)

    # Translate so that min_x == 0, min_y == 0
    def translate(e: Entity, dx: float, dy: float) -> None:
        e.translate(dx, dy)

    shift_x = -min_x + margin_mm
    shift_y = -min_y + margin_mm

    # Work on clones to avoid mutating document
    import copy
    clones = [copy.deepcopy(e) for e in entities]
    for c in clones:
        c.translate(shift_x, shift_y)

    w_mm = (max_x - min_x) + 2 * margin_mm
    h_mm = (max_y - min_y) + 2 * margin_mm
    # y_max in translated coords = (max_y - min_y)
    y_max_t = max_y - min_y + margin_mm

    layer_colors: dict[str, str] = {
        l.name: l.color for l in document.layers
    }

    svg_lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w_mm:.4f}mm" height="{h_mm:.4f}mm" '
        f'viewBox="0 0 {w_mm:.4f} {h_mm:.4f}">',
        '  <!-- ChandramaCAD SVG Export — Chandrama Solutions -->',
        f'  <rect width="{w_mm:.4f}" height="{h_mm:.4f}" fill="white"/>',
    ]

    for clone in clones:
        layer_color = layer_colors.get(clone.layer, "#1A1A24")
        svg_lines.extend(_entity_svg(clone, layer_color, y_max_t, margin=0))

    svg_lines.append("</svg>")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_lines))


# ── PDF Export ────────────────────────────────────────────────────────────────

def export_pdf(document: Document, path: str, margin_mm: float = 10.0) -> None:
    """
    Export all visible entities to a PDF using Qt's PDF writer.
    Entities are rendered with QPainter — same visual fidelity as the canvas.
    """
    from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPageSize, QPageLayout
    from PySide6.QtCore import QSizeF, QRectF, QPointF, QMarginsF
    try:
        from PySide6.QtGui import QPdfWriter
    except ImportError:
        from PySide6.QtPrintSupport import QPrinter as QPdfWriter   # fallback

    entities = document.visible_entities()
    if not entities:
        raise ValueError("No visible entities to export.")

    all_bb = [e.bounding_box() for e in entities]
    min_x = min(bb[0] for bb in all_bb)
    min_y = min(bb[1] for bb in all_bb)
    max_x = max(bb[2] for bb in all_bb)
    max_y = max(bb[3] for bb in all_bb)

    w_mm = (max_x - min_x) + 2 * margin_mm
    h_mm = (max_y - min_y) + 2 * margin_mm

    try:
        writer = QPdfWriter(path)
        page_size = QPageSize(QSizeF(w_mm, h_mm), QPageSize.Unit.Millimeter)
        writer.setPageSize(page_size)
        writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        writer.setResolution(300)   # 300 DPI
        dpi = 300.0
    except Exception:
        raise RuntimeError("QPdfWriter not available; install PySide6-Addons or QtPrintSupport.")

    scale = dpi / 25.4          # pixels per mm at 300 DPI

    layer_colors: dict[str, str] = {l.name: l.color for l in document.layers}

    painter = QPainter()
    if not painter.begin(writer):
        raise RuntimeError(f"Cannot open PDF for writing: {path}")

    try:
        def world_to_pdf(wx: float, wy: float) -> tuple[float, float]:
            """Convert world mm coords to PDF device pixels (Y flipped)."""
            px = (wx - min_x + margin_mm) * scale
            py = (max_y - wy + margin_mm) * scale
            return px, py

        def draw_polyline(pts: np.ndarray, pen: QPen, closed: bool = False) -> None:
            if len(pts) < 2:
                return
            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            poly = QPolygonF()
            for p in pts:
                px, py = world_to_pdf(float(p[0]), float(p[1]))
                poly.append(QPointF(px, py))
            painter.setPen(pen)
            if closed:
                painter.drawPolygon(poly)
            else:
                painter.drawPolyline(poly)

        def entity_pen(e: Entity) -> QPen:
            hex_c = e.color if e.color else layer_colors.get(e.layer, "#1A1A24")
            r, g, b = hex_to_rgb(hex_c)
            pen = QPen(QColor(r, g, b))
            pen.setWidthF(0.5 * scale / 25.4)   # 0.5mm stroke in device units
            pen.setCosmetic(False)
            return pen

        for entity in entities:
            pen = entity_pen(entity)

            if isinstance(entity, LineEntity):
                px1, py1 = world_to_pdf(float(entity.start[0]), float(entity.start[1]))
                px2, py2 = world_to_pdf(float(entity.end[0]), float(entity.end[1]))
                painter.setPen(pen)
                painter.drawLine(QPointF(px1, py1), QPointF(px2, py2))

            elif isinstance(entity, (PolylineEntity, RectangleEntity,
                                     PolygonEntity, SplineEntity,
                                     SemiCircleEntity, GrooveEntity)):
                pts = entity.to_points()
                closed = (isinstance(entity, (RectangleEntity, PolygonEntity))
                          or getattr(entity, "closed", False))
                draw_polyline(pts, pen, closed)

            elif isinstance(entity, CircleEntity):
                cx, cy = world_to_pdf(float(entity.center[0]), float(entity.center[1]))
                r_px = entity.radius * scale
                painter.setPen(pen)
                painter.setBrush(QColor(0, 0, 0, 0))
                painter.drawEllipse(QPointF(cx, cy), r_px, r_px)

            elif isinstance(entity, ArcEntity):
                pts = entity.to_points(128)
                draw_polyline(pts, pen, False)

            elif isinstance(entity, EllipseEntity):
                pts = entity.to_points(128)
                draw_polyline(pts, pen, True)

            elif isinstance(entity, PointEntity):
                px, py = world_to_pdf(float(entity.position[0]), float(entity.position[1]))
                r_px = 1.0 * scale
                painter.setPen(pen)
                painter.setBrush(pen.color())
                painter.drawEllipse(QPointF(px, py), r_px, r_px)

            elif isinstance(entity, TextEntity):
                px, py = world_to_pdf(float(entity.position[0]), float(entity.position[1]))
                font = QFont("Arial", max(1, int(entity.height * scale * 0.6)))
                painter.setFont(font)
                painter.setPen(pen)
                painter.drawText(QPointF(px, py), entity.text)

            elif isinstance(entity, DimLinearEntity):
                pts = entity.to_points()
                draw_polyline(pts, pen, False)
                # Measurement text
                mid = (entity.p1 + entity.p2) / 2
                tx, ty = world_to_pdf(float(mid[0]), float(mid[1] + abs(entity.offset) + 2))
                font = QFont("Arial", max(1, int(3.5 * scale * 0.6)))
                painter.setFont(font)
                painter.setPen(pen)
                painter.drawText(QPointF(tx, ty), f"{entity.measurement():.2f}")

            elif isinstance(entity, DimRadialEntity):
                pts = entity.to_points()
                draw_polyline(pts, pen, False)
                tip = pts[-1]
                tx, ty = world_to_pdf(float(tip[0]) + 2, float(tip[1]))
                prefix = "⌀" if entity.is_diameter else "R"
                val = entity.radius * (2 if entity.is_diameter else 1)
                font = QFont("Arial", max(1, int(3.5 * scale * 0.6)))
                painter.setFont(font)
                painter.setPen(pen)
                painter.drawText(QPointF(tx, ty), f"{prefix}{val:.2f}")

    finally:
        painter.end()
