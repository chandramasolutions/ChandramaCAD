"""
ChandramaCAD – DXF Import via ezdxf.
Converts DXF entities to native ChandramaCAD entity objects.
Supported: LINE, LWPOLYLINE, POLYLINE, CIRCLE, ARC, ELLIPSE,
           SPLINE, TEXT, MTEXT, POINT, INSERT (expanded via virtual layout).
"""
from __future__ import annotations
import math
from typing import Optional
import numpy as np

from core.document import Document, Layer
from core.entities import (
    LineEntity, PolylineEntity, CircleEntity, ArcEntity,
    EllipseEntity, SplineEntity, TextEntity, PointEntity,
)
from core.color_utils import aci_to_hex


def import_dxf(path: str) -> Document:
    """
    Read a DXF file and return a new ChandramaCAD Document.
    All entities from modelspace are imported.
    Raises on IO / parse error.
    """
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    try:
        dxf_doc = ezdxf.readfile(path)
    except Exception as exc:
        raise IOError(f"Cannot read DXF file: {exc}") from exc

    doc = Document()
    doc.layers.clear()

    # ── Import layers ────────────────────────────────────────────────────────
    default_added = False
    for dxf_layer in dxf_doc.layers:
        lname = dxf_layer.dxf.name
        if lname == "0":
            lname = "Default"   # map DXF layer 0 → Default

        # Colour: prefer true_color (24-bit), fall back to ACI
        hex_color = "#1A1A24"
        try:
            if dxf_layer.has_dxf_attrib("true_color"):
                tc = dxf_layer.dxf.true_color
                r = (tc >> 16) & 0xFF
                g = (tc >> 8) & 0xFF
                b = tc & 0xFF
                hex_color = f"#{r:02X}{g:02X}{b:02X}"
            elif dxf_layer.has_dxf_attrib("color"):
                hex_color = aci_to_hex(abs(dxf_layer.dxf.color))
        except Exception:
            pass

        visible = True
        try:
            visible = not dxf_layer.is_frozen
        except Exception:
            pass

        linetype = "CONTINUOUS"
        try:
            lt = dxf_layer.dxf.linetype
            if lt and lt.upper() != "BYLAYER":
                linetype = lt.upper()
        except Exception:
            pass

        layer = Layer(lname, hex_color, visible, linetype)
        doc.layers.append(layer)
        if lname == "Default":
            default_added = True

    if not default_added:
        doc.layers.insert(0, Layer("Default", "#1A1A24"))
    doc.active_layer = doc.layers[0].name

    # Helper: entity's layer name (map "0" → "Default")
    def _layer(e) -> str:
        try:
            ln = e.dxf.layer
            return "Default" if ln == "0" else ln
        except Exception:
            return "Default"

    # Helper: entity hex colour
    def _color(e) -> Optional[str]:
        try:
            if e.has_dxf_attrib("true_color"):
                tc = e.dxf.true_color
                r = (tc >> 16) & 0xFF
                g = (tc >> 8) & 0xFF
                b = tc & 0xFF
                return f"#{r:02X}{g:02X}{b:02X}"
            aci = e.dxf.color
            if aci not in (0, 256):   # 0=BYBLOCK, 256=BYLAYER → use layer colour
                return aci_to_hex(aci)
        except Exception:
            pass
        return None

    def _linetype(e) -> str:
        try:
            lt = e.dxf.linetype
            if lt and lt.upper() not in ("BYLAYER", "BYBLOCK"):
                return lt.upper()
        except Exception:
            pass
        return "CONTINUOUS"

    def _attach(entity, dxf_e) -> None:
        entity.layer = _layer(dxf_e)
        c = _color(dxf_e)
        if c:
            entity.color = c
        entity.linetype = _linetype(dxf_e)
        doc.entities.append(entity)

    # ── Import modelspace entities ───────────────────────────────────────────
    msp = dxf_doc.modelspace()

    for e in msp:
        etype = e.dxftype()

        try:
            if etype == "LINE":
                s = e.dxf.start
                en = e.dxf.end
                ent = LineEntity(
                    np.array([float(s.x), float(s.y)]),
                    np.array([float(en.x), float(en.y)]),
                )
                _attach(ent, e)

            elif etype == "LWPOLYLINE":
                pts = [np.array([float(p[0]), float(p[1])]) for p in e.get_points()]
                if len(pts) >= 2:
                    closed = bool(e.closed)
                    ent = PolylineEntity(pts, closed)
                    _attach(ent, e)

            elif etype == "POLYLINE":
                # 2D POLYLINE (MESH/3D-MESH excluded)
                try:
                    verts = [np.array([float(v.dxf.location.x), float(v.dxf.location.y)])
                             for v in e.vertices]
                    if len(verts) >= 2:
                        closed = bool(e.is_closed)
                        ent = PolylineEntity(verts, closed)
                        _attach(ent, e)
                except Exception:
                    pass

            elif etype == "CIRCLE":
                c = e.dxf.center
                ent = CircleEntity(
                    np.array([float(c.x), float(c.y)]),
                    float(e.dxf.radius),
                )
                _attach(ent, e)

            elif etype == "ARC":
                c = e.dxf.center
                ent = ArcEntity(
                    np.array([float(c.x), float(c.y)]),
                    float(e.dxf.radius),
                    float(e.dxf.start_angle),
                    float(e.dxf.end_angle),
                )
                _attach(ent, e)

            elif etype == "ELLIPSE":
                c = e.dxf.center
                major = e.dxf.major_axis
                ratio = float(e.dxf.ratio)
                rx = float(math.sqrt(major.x ** 2 + major.y ** 2))
                ry = rx * ratio
                rot_deg = math.degrees(math.atan2(float(major.y), float(major.x)))
                ent = EllipseEntity(
                    np.array([float(c.x), float(c.y)]),
                    rx, ry, rot_deg,
                )
                _attach(ent, e)

            elif etype == "SPLINE":
                try:
                    fit_pts = e.fit_points
                    if fit_pts is not None and len(fit_pts) >= 2:
                        pts = [np.array([float(p[0]), float(p[1])]) for p in fit_pts]
                    else:
                        ctrl = e.control_points
                        pts = [np.array([float(p[0]), float(p[1])]) for p in ctrl]
                    if len(pts) >= 2:
                        ent = SplineEntity(pts)
                        _attach(ent, e)
                except Exception:
                    pass

            elif etype in ("TEXT", "ATTDEF"):
                try:
                    ins = e.dxf.insert
                    ent = TextEntity(
                        np.array([float(ins.x), float(ins.y)]),
                        str(e.dxf.text),
                        float(e.dxf.height) if e.has_dxf_attrib("height") else 5.0,
                        float(e.dxf.rotation) if e.has_dxf_attrib("rotation") else 0.0,
                    )
                    _attach(ent, e)
                except Exception:
                    pass

            elif etype == "MTEXT":
                try:
                    ins = e.dxf.insert
                    text = e.plain_text()
                    ent = TextEntity(
                        np.array([float(ins.x), float(ins.y)]),
                        text,
                        float(e.dxf.char_height) if e.has_dxf_attrib("char_height") else 5.0,
                        float(e.dxf.rotation) if e.has_dxf_attrib("rotation") else 0.0,
                    )
                    _attach(ent, e)
                except Exception:
                    pass

            elif etype == "POINT":
                loc = e.dxf.location
                ent = PointEntity(np.array([float(loc.x), float(loc.y)]))
                _attach(ent, e)

            elif etype == "INSERT":
                # Expand block reference to constituent entities
                try:
                    for sub_e in e.virtual_entities():
                        # Recurse one level (blocks can contain basic entities)
                        msp.__class__  # just a probe; iterate virtual list
                        sub_etype = sub_e.dxftype()
                        if sub_etype == "LINE":
                            s2, e2 = sub_e.dxf.start, sub_e.dxf.end
                            ent2 = LineEntity(
                                np.array([float(s2.x), float(s2.y)]),
                                np.array([float(e2.x), float(e2.y)]),
                            )
                            _attach(ent2, sub_e)
                        elif sub_etype == "LWPOLYLINE":
                            pts2 = [np.array([float(p[0]), float(p[1])]) for p in sub_e.get_points()]
                            if len(pts2) >= 2:
                                ent2 = PolylineEntity(pts2, bool(sub_e.closed))
                                _attach(ent2, sub_e)
                        elif sub_etype == "CIRCLE":
                            c2 = sub_e.dxf.center
                            ent2 = CircleEntity(
                                np.array([float(c2.x), float(c2.y)]),
                                float(sub_e.dxf.radius),
                            )
                            _attach(ent2, sub_e)
                        elif sub_etype == "ARC":
                            c2 = sub_e.dxf.center
                            ent2 = ArcEntity(
                                np.array([float(c2.x), float(c2.y)]),
                                float(sub_e.dxf.radius),
                                float(sub_e.dxf.start_angle),
                                float(sub_e.dxf.end_angle),
                            )
                            _attach(ent2, sub_e)
                except Exception:
                    pass   # skip blocks that fail to expand

        except Exception:
            pass   # skip entities that fail to parse

    if not doc.entities:
        # If nothing imported, at least the layers are set up correctly
        pass

    return doc
