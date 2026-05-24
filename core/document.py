from __future__ import annotations
import json
import copy
from typing import Optional
from core.entities import (
    Entity, LineEntity, PolylineEntity, RectangleEntity,
    CircleEntity, ArcEntity, SplineEntity,
    PolygonEntity, EllipseEntity, SemiCircleEntity, GrooveEntity,
    PointEntity, TextEntity, DimLinearEntity, DimRadialEntity,
)
import numpy as np


class Layer:
    def __init__(self, name: str, color: str = "#1A1A24", visible: bool = True,
                 linetype: str = "CONTINUOUS", lineweight: int = -3):
        self.name = name
        self.color = color
        self.visible = visible
        self.linetype = linetype      # DXF linetype name
        self.lineweight = lineweight  # DXF lineweight in 100ths of mm (-3 = BYLAYER default)

    def to_dict(self):
        return {
            "name":       self.name,
            "color":      self.color,
            "visible":    self.visible,
            "linetype":   self.linetype,
            "lineweight": self.lineweight,
        }

    @staticmethod
    def from_dict(d):
        return Layer(
            d["name"],
            d.get("color", "#1A1A24"),
            d.get("visible", True),
            d.get("linetype", "CONTINUOUS"),
            d.get("lineweight", -3),
        )


class Document:
    def __init__(self):
        self.layers: list[Layer] = [Layer("Default", "#1A1A24")]
        self.entities: list[Entity] = []
        self.active_layer: str = "Default"
        self._undo_stack: list[tuple] = []
        self._redo_stack: list[tuple] = []
        self._modified: bool = False

    # ── Undo / Redo ─────────────────────────────────────

    def _snapshot(self):
        return (
            copy.deepcopy(self.layers),
            copy.deepcopy(self.entities),
            self.active_layer,
        )

    def _push_undo(self, snapshot):
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()
        self._modified = True

    def begin_operation(self):
        return self._snapshot()

    def commit_operation(self, snapshot):
        self._push_undo(snapshot)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._snapshot())
        layers, entities, active = self._undo_stack.pop()
        self.layers = layers
        self.entities = entities
        self.active_layer = active
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._snapshot())
        layers, entities, active = self._redo_stack.pop()
        self.layers = layers
        self.entities = entities
        self.active_layer = active
        return True

    # ── Layers ───────────────────────────────────────────

    def layer_names(self) -> list[str]:
        return [l.name for l in self.layers]

    def get_layer(self, name: str) -> Optional[Layer]:
        for l in self.layers:
            if l.name == name:
                return l
        return None

    def add_layer(self, name: str, color: str = "#1A1A24") -> Layer:
        snap = self._snapshot()
        if self.get_layer(name):
            return self.get_layer(name)
        layer = Layer(name, color)
        self.layers.append(layer)
        self._push_undo(snap)
        return layer

    def remove_layer(self, name: str):
        if name == "Default" or name == self.active_layer:
            return False
        snap = self._snapshot()
        self.layers = [l for l in self.layers if l.name != name]
        self.entities = [e for e in self.entities if e.layer != name]
        self._push_undo(snap)
        return True

    def rename_layer(self, old_name: str, new_name: str) -> bool:
        if new_name in self.layer_names():
            return False
        snap = self._snapshot()
        for l in self.layers:
            if l.name == old_name:
                l.name = new_name
        for e in self.entities:
            if e.layer == old_name:
                e.layer = new_name
        if self.active_layer == old_name:
            self.active_layer = new_name
        self._push_undo(snap)
        return True

    def set_layer_color(self, name: str, color: str):
        snap = self._snapshot()
        layer = self.get_layer(name)
        if layer:
            layer.color = color
            self._push_undo(snap)

    def toggle_layer_visibility(self, name: str):
        snap = self._snapshot()
        layer = self.get_layer(name)
        if layer:
            layer.visible = not layer.visible
            self._push_undo(snap)

    # ── Entities ─────────────────────────────────────────

    def add_entity(self, entity: Entity, push_undo: bool = True) -> Entity:
        snap = self._snapshot() if push_undo else None
        entity.layer = self.active_layer
        self.entities.append(entity)
        if push_undo and snap is not None:
            self._push_undo(snap)
        return entity

    def remove_entities(self, ids: list[int]):
        snap = self._snapshot()
        self.entities = [e for e in self.entities if e.id not in ids]
        self._push_undo(snap)

    def all_entities(self) -> list[Entity]:
        return list(self.entities)

    def visible_entities(self) -> list[Entity]:
        visible_layers = {l.name for l in self.layers if l.visible}
        return [e for e in self.entities if e.layer in visible_layers]

    def selected_entities(self) -> list[Entity]:
        return [e for e in self.entities if e.selected]

    def select_all(self):
        for e in self.entities:
            e.selected = True

    def deselect_all(self):
        for e in self.entities:
            e.selected = False

    def entity_by_id(self, eid: int) -> Optional[Entity]:
        for e in self.entities:
            if e.id == eid:
                return e
        return None

    # ── Persistence ──────────────────────────────────────

    def to_dict(self) -> dict:
        def entity_to_dict(e: Entity) -> dict:
            d: dict = {
                "type":     type(e).__name__,
                "layer":    e.layer,
                "color":    e.color,
                "linetype": getattr(e, "linetype", "CONTINUOUS"),
            }
            if isinstance(e, LineEntity):
                d["start"] = list(e.start)
                d["end"] = list(e.end)
            elif isinstance(e, PolylineEntity):
                d["points"] = [list(p) for p in e.points]
                d["closed"] = e.closed
            elif isinstance(e, RectangleEntity):
                d["corner1"] = list(e.corner1)
                d["corner2"] = list(e.corner2)
            elif isinstance(e, CircleEntity):
                d["center"] = list(e.center)
                d["radius"] = e.radius
            elif isinstance(e, ArcEntity):
                d["center"] = list(e.center)
                d["radius"] = e.radius
                d["start_angle"] = e.start_angle
                d["end_angle"] = e.end_angle
            elif isinstance(e, SplineEntity):
                d["control_points"] = [list(p) for p in e.control_points]
            elif isinstance(e, PolygonEntity):
                d["center"] = list(e.center)
                d["n_sides"] = e.n_sides
                d["circumradius"] = e.circumradius
                d["rotation_deg"] = e.rotation_deg
            elif isinstance(e, EllipseEntity):
                d["center"] = list(e.center)
                d["rx"] = e.rx
                d["ry"] = e.ry
                d["rotation_deg"] = e.rotation_deg
            elif isinstance(e, SemiCircleEntity):
                d["center"] = list(e.center)
                d["radius"] = e.radius
                d["flat_angle"] = e.flat_angle
            elif isinstance(e, GrooveEntity):
                d["center1"] = list(e.center1)
                d["center2"] = list(e.center2)
                d["radius"] = e.radius
            elif isinstance(e, PointEntity):
                d["position"] = list(e.position)
            elif isinstance(e, TextEntity):
                d["position"] = list(e.position)
                d["text"] = e.text
                d["height"] = e.height
                d["rotation_deg"] = e.rotation_deg
            elif isinstance(e, DimLinearEntity):
                d["p1"] = list(e.p1)
                d["p2"] = list(e.p2)
                d["offset"] = e.offset
            elif isinstance(e, DimRadialEntity):
                d["center"] = list(e.center)
                d["radius"] = e.radius
                d["angle_deg"] = e.angle_deg
                d["is_diameter"] = e.is_diameter
            return d

        return {
            "version": "1.0",
            "active_layer": self.active_layer,
            "layers": [l.to_dict() for l in self.layers],
            "entities": [entity_to_dict(e) for e in self.entities],
        }

    @staticmethod
    def from_dict(d: dict) -> "Document":
        doc = Document()
        doc.layers = [Layer.from_dict(l) for l in d.get("layers", [])]
        if not doc.layers:
            doc.layers = [Layer("Default")]
        doc.active_layer = d.get("active_layer", doc.layers[0].name)

        def entity_from_dict(ed: dict) -> Optional[Entity]:
            t = ed.get("type", "")
            e: Optional[Entity] = None
            if t == "LineEntity":
                e = LineEntity(np.array(ed["start"]), np.array(ed["end"]))
            elif t == "PolylineEntity":
                e = PolylineEntity([np.array(p) for p in ed["points"]], ed.get("closed", False))
            elif t == "RectangleEntity":
                e = RectangleEntity(np.array(ed["corner1"]), np.array(ed["corner2"]))
            elif t == "CircleEntity":
                e = CircleEntity(np.array(ed["center"]), ed["radius"])
            elif t == "ArcEntity":
                e = ArcEntity(np.array(ed["center"]), ed["radius"], ed["start_angle"], ed["end_angle"])
            elif t == "SplineEntity":
                e = SplineEntity([np.array(p) for p in ed["control_points"]])
            elif t == "PolygonEntity":
                e = PolygonEntity(np.array(ed["center"]), ed["n_sides"],
                                  ed["circumradius"], ed.get("rotation_deg", 90.0))
            elif t == "EllipseEntity":
                e = EllipseEntity(np.array(ed["center"]), ed["rx"], ed["ry"],
                                  ed.get("rotation_deg", 0.0))
            elif t == "SemiCircleEntity":
                e = SemiCircleEntity(np.array(ed["center"]), ed["radius"],
                                     ed.get("flat_angle", 0.0))
            elif t == "GrooveEntity":
                e = GrooveEntity(np.array(ed["center1"]), np.array(ed["center2"]),
                                 ed["radius"])
            elif t == "PointEntity":
                e = PointEntity(np.array(ed["position"]))
            elif t == "TextEntity":
                e = TextEntity(np.array(ed["position"]), ed["text"],
                               ed.get("height", 5.0), ed.get("rotation_deg", 0.0))
            elif t == "DimLinearEntity":
                e = DimLinearEntity(np.array(ed["p1"]), np.array(ed["p2"]),
                                    ed.get("offset", 10.0))
            elif t == "DimRadialEntity":
                e = DimRadialEntity(np.array(ed["center"]), ed["radius"],
                                    ed.get("angle_deg", 0.0), ed.get("is_diameter", False))
            if e is not None:
                e.layer    = ed.get("layer", "Default")
                e.color    = ed.get("color")
                e.linetype = ed.get("linetype", "CONTINUOUS")
            return e

        for ed in d.get("entities", []):
            ent = entity_from_dict(ed)
            if ent is not None:
                doc.entities.append(ent)

        return doc

    def save_to_file(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        self._modified = False

    @staticmethod
    def load_from_file(path: str) -> "Document":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        doc = Document.from_dict(data)
        doc._modified = False
        return doc

    @property
    def is_modified(self) -> bool:
        return self._modified
