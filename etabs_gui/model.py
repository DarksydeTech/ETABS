"""Modelo de proyecto ETABS CIXTOP en memoria (sin dependencia de Excel).

El proyecto se guarda como JSON y puede importarse una sola vez desde el
libro 4.0 para reutilizar sus valores. Todas las operaciones de generación,
edición y exportación trabajan sobre este modelo.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import plan as plan_engine
from . import template


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(to_float(value, float(default)))
    except (TypeError, ValueError):
        return default


def column_letter(index: int) -> str:
    """1 -> A, 27 -> AA."""
    result = ""
    n = max(int(index), 1)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


@dataclass
class Issue:
    severity: str
    message: str
    area: str = ""
    item: str = ""


# --------------------------------------------------------------------------
# Proyecto
# --------------------------------------------------------------------------

class Project:
    def __init__(self) -> None:
        self.name: str = ""
        self.description: str = ""
        self.stories: list[dict] = []
        self.grid_x: list[dict] = []
        self.grid_y: list[dict] = []
        self.inclined_x: list[dict] = []
        self.inclined_y: list[dict] = []
        self.spacing_x: float = 3.0
        self.spacing_y: float = 2.0
        self.materials: list[dict] = []
        self.section_counts: dict[str, int] = {}
        self.frame_sections: list[dict] = []
        self.slabs: list[dict] = []
        self.walls: list[dict] = []
        self.patterns: list[dict] = []
        self.seismic: dict = {}
        self.mass_source: dict = {}
        self.combos: list[dict] = []
        self.assignments: dict = {
            "column_sections": {},
            "beam_sections": {},
            "slab_sections": {},
            "wall_defs": [],
        }
        self.plan: plan_engine.Plan = plan_engine.Plan()
        self.path: Path | None = None
        self.dirty: bool = False

    # -- creación ---------------------------------------------------------
    @classmethod
    def new(cls) -> "Project":
        p = cls()
        p.name = template.DEFAULT_PROJECT["name"]
        p.description = template.DEFAULT_PROJECT["description"]
        p.spacing_x = template.DEFAULT_GRID_X["spacing"]
        p.spacing_y = template.DEFAULT_GRID_Y["spacing"]
        p.materials = copy.deepcopy(template.DEFAULT_MATERIALS)
        p.section_counts = copy.deepcopy(template.DEFAULT_SECTION_COUNTS)
        p.slabs = copy.deepcopy(template.DEFAULT_SLABS)
        p.walls = copy.deepcopy(template.DEFAULT_WALLS)
        p.patterns = copy.deepcopy(template.DEFAULT_PATTERNS)
        p.seismic = copy.deepcopy(template.DEFAULT_SEISMIC)
        p.mass_source = copy.deepcopy(template.DEFAULT_MASS_SOURCE)
        p.combos = copy.deepcopy(template.DEFAULT_COMBOS)
        p.stories = _build_stories(template.DEFAULT_PROJECT["stories_count"],
                                   template.DEFAULT_PROJECT["typical_height"],
                                   template.DEFAULT_PROJECT["first_height"])
        p.grid_x = _build_grids("X", template.DEFAULT_GRID_X["coords"])
        p.grid_y = _build_grids("Y", template.DEFAULT_GRID_Y["coords"])
        p.inclined_x = copy.deepcopy(template.DEFAULT_INCLINED_X)
        p.inclined_y = copy.deepcopy(template.DEFAULT_INCLINED_Y)
        p.generate_frame_sections()
        p.assignments["wall_defs"] = _starter_walls(p)
        p.generate_plan()
        p.dirty = False
        return p

    # -- historias / grillas ---------------------------------------------
    def generate_stories(self, count: int | None = None,
                         typical: float | None = None,
                         first: float | None = None) -> int:
        count = template.DEFAULT_PROJECT["stories_count"] if count is None else count
        typical = template.DEFAULT_PROJECT["typical_height"] if typical is None else typical
        first = template.DEFAULT_PROJECT["first_height"] if first is None else first
        count = max(1, min(to_int(count, 1), 50))
        typical = to_float(typical, 3.0)
        first = to_float(first, typical)
        if typical <= 0:
            typical = 3.0
        if first <= 0:
            first = typical
        self.stories = _build_stories(count, typical, first)
        self.dirty = True
        return count

    def generate_grids(self, axis: str) -> int:
        axis = axis.upper()
        if axis == "X":
            count = max(1, min(len(self.grid_x), 50))
            spacing = self.spacing_x if self.spacing_x > 0 else 3.0
            self.grid_x = _build_grids("X", [i * spacing for i in range(count)])
        elif axis == "Y":
            count = max(1, min(len(self.grid_y), 50))
            spacing = self.spacing_y if self.spacing_y > 0 else 2.0
            self.grid_y = _build_grids("Y", [i * spacing for i in range(count)])
        else:
            raise ValueError("El eje debe ser X o Y.")
        self.generate_plan()
        self.dirty = True
        return count

    def add_grid(self, axis: str, coord: float | None = None) -> int:
        axis = axis.upper()
        grids = self.grid_x if axis == "X" else self.grid_y
        if len(grids) >= 50:
            raise ValueError("La plantilla admite como máximo 50 grillas por eje.")
        if coord is None:
            coord = (grids[-1]["coord"] + (self.spacing_x if axis == "X" else self.spacing_y)) if grids else 0.0
        ids = {g["id"] for g in grids}
        grid_id = None
        for index in range(1, 60):
            candidate = column_letter(index) if axis == "X" else str(index)
            if candidate not in ids:
                grid_id = candidate
                break
        grids.append({"id": grid_id, "coord": float(coord)})
        self.generate_plan()
        self.dirty = True
        return len(grids)

    def grid_assignments(self) -> None:
        """Recalcula coordenadas derivadas (separaciones) tras editar."""
        for grids in (self.grid_x, self.grid_y):
            for index, grid in enumerate(grids):
                nxt = grids[index + 1]["coord"] if index + 1 < len(grids) else None
                grid["spacing"] = 0.0 if nxt is None else float(nxt) - float(grid["coord"])

    # -- secciones --------------------------------------------------------
    def generate_frame_sections(self) -> int:
        groups_by_prefix = {g["prefix"]: g for g in template.DEFAULT_SECTION_GROUPS}
        existing = {s["name"]: s for s in self.frame_sections}
        sections: list[dict] = []
        for group in template.DEFAULT_SECTION_GROUPS:
            count = max(0, min(to_int(self.section_counts.get(group["count_key"], 0), 0), 50))
            for index in range(1, count + 1):
                defaults = template.frame_section_defaults(group, index)
                if defaults["name"] in existing:
                    current = copy.deepcopy(existing[defaults["name"]])
                    current.setdefault("element", defaults["element"])
                    current["area"] = template.section_properties(
                        current.get("geometry", ""), current.get("d", 0),
                        current.get("bf", 0), current.get("tw", 0), current.get("tf", 0))[0]
                    current["inertia"] = template.section_properties(
                        current.get("geometry", ""), current.get("d", 0),
                        current.get("bf", 0), current.get("tw", 0), current.get("tf", 0))[1]
                    sections.append(current)
                else:
                    sections.append(defaults)
        self.frame_sections = sections
        self._prune_assignments()
        self.generate_plan()
        self.dirty = True
        return len(sections)

    def refresh_section_properties(self) -> None:
        for section in self.frame_sections:
            area, inertia = template.section_properties(
                section.get("geometry", ""), section.get("d", 0),
                section.get("bf", 0), section.get("tw", 0), section.get("tf", 0))
            section["area"] = area
            section["inertia"] = inertia

    def rename_section(self, old: str, new: str) -> int:
        """Renombra una sección en su definición y en todas sus asignaciones.

        Devuelve la cantidad de asignaciones actualizadas, o -1 si el nombre
        nuevo ya existe. Un nombre vacío o igual devuelve 0 sin cambios.
        """
        old = str(old).strip()
        new = str(new).strip()
        if not old or not new or old == new:
            return 0
        existing = {str(s.get("name", "")).strip().lower() for s in self.frame_sections
                    if str(s.get("name", "")).strip() != old}
        if new.lower() in existing:
            return -1
        for section in self.frame_sections:
            if str(section.get("name", "")).strip() == old:
                section["name"] = new
        changed = 0
        for key in ("column_sections", "beam_sections"):
            mapping = self.assignments.get(key, {})
            for item, name in list(mapping.items()):
                if name == old:
                    mapping[item] = new
                    changed += 1
            self.assignments[key] = mapping
        self.dirty = True
        return changed

    def rename_material(self, old: str, new: str) -> int:
        """Renombra un material en su definición y en las secciones que lo usan.

        Devuelve la cantidad de referencias actualizadas, o -1 si el nombre
        nuevo ya existe.
        """
        old = str(old).strip()
        new = str(new).strip()
        if not old or not new or old == new:
            return 0
        existing = {str(m.get("name", "")).strip().lower() for m in self.materials
                    if str(m.get("name", "")).strip() != old}
        if new.lower() in existing:
            return -1
        for material in self.materials:
            if str(material.get("name", "")).strip() == old:
                material["name"] = new
        changed = 0
        for item in self.frame_sections + self.slabs + self.walls:
            if str(item.get("material", "")).strip() == old:
                item["material"] = new
                changed += 1
        self.dirty = True
        return changed

    def section_names(self, element: str = "") -> list[str]:
        if not element:
            return [s["name"] for s in self.frame_sections]
        needle = element.lower()
        return [s["name"] for s in self.frame_sections
                if needle in str(s.get("element", "")).lower()]

    def generate_area_sections(self) -> tuple[int, int]:
        # Los datos de losas y muros ya son listas editables; se valida y se
        # aplican los modificadores por defecto que falten.
        for slab in self.slabs:
            slab.setdefault("mods", [1.0] * 7)
        for wall in self.walls:
            wall.setdefault("mods", [1.0, 1.0, 1.0, 0.6, 0.6, 0.6, 1.0])
        if not self.slabs:
            self.slabs = copy.deepcopy(template.DEFAULT_SLABS)
        if not self.walls:
            self.walls = copy.deepcopy(template.DEFAULT_WALLS)
        self.generate_plan()
        self.dirty = True
        return len(self.slabs), len(self.walls)

    def generate_loads(self) -> None:
        self.patterns = copy.deepcopy(template.DEFAULT_PATTERNS)
        self.seismic = copy.deepcopy(template.DEFAULT_SEISMIC)
        self.mass_source = copy.deepcopy(template.DEFAULT_MASS_SOURCE)
        self.combos = copy.deepcopy(template.DEFAULT_COMBOS)
        self.dirty = True

    def all_pattern_names(self) -> list[str]:
        names = [str(p.get("name", "")).strip() for p in self.patterns]
        names += [str(p.get("name", "")).strip() for p in self.seismic.get("patterns", [])]
        return [n for n in names if n]

    # -- planta -----------------------------------------------------------
    def default_section(self, element: str) -> str:
        names = self.section_names(element)
        return names[0] if names else ""

    def generate_plan(self) -> plan_engine.Plan:
        slab_names = [s["name"] for s in self.slabs]
        wall_names = [w["name"] for w in self.walls]
        self.plan = plan_engine.build_plan(
            [(g["id"], to_float(g["coord"])) for g in self.grid_x],
            [(g["id"], to_float(g["coord"])) for g in self.grid_y],
            self.inclined_x, self.inclined_y,
            column_sections=self.assignments.get("column_sections", {}),
            beam_sections=self.assignments.get("beam_sections", {}),
            wall_defs=self.assignments.get("wall_defs", []),
            slab_sections=self.assignments.get("slab_sections", {}),
            default_column=self.default_section("columna"),
            default_beam=self.default_section("viga"),
            default_wall=wall_names[0] if wall_names else "",
            default_slab=slab_names[0] if slab_names else "VACIO",
        )
        self._sync_assignments_from_plan()
        self.grid_assignments()
        self.dirty = True
        return self.plan

    def _sync_assignments_from_plan(self) -> None:
        self.assignments["column_sections"] = {
            c.id: c.section for c in self.plan.columns if c.section}
        self.assignments["beam_sections"] = {
            b.id: b.section for b in self.plan.beams if b.section}
        self.assignments["slab_sections"] = {
            s.id: s.section for s in self.plan.slabs if s.section}
        definitions = self.assignments.get("wall_defs", [])
        by_id = {str(d.get("id", "")): d for d in definitions}
        for wall in self.plan.walls:
            by_id[wall.id] = {"id": wall.id, "a": wall.col_a,
                              "b": wall.col_b, "section": wall.section}
        self.assignments["wall_defs"] = list(by_id.values())

    def _prune_assignments(self) -> None:
        valid = {s["name"] for s in self.frame_sections}
        for key in ("column_sections", "beam_sections"):
            self.assignments[key] = {
                name: section for name, section in self.assignments.get(key, {}).items()
                if section in valid}

    def set_wall_definitions(self, definitions: list[dict]) -> None:
        self.assignments["wall_defs"] = [
            {"id": str(d.get("id", "")).strip(),
             "a": str(d.get("a", "")).strip(),
             "b": str(d.get("b", "")).strip(),
             "section": str(d.get("section", "")).strip()}
            for d in definitions]
        self.generate_plan()

    # -- validación -------------------------------------------------------
    def validate(self) -> list[Issue]:
        issues: list[Issue] = []
        if not self.stories:
            issues.append(Issue("error", "No hay niveles definidos.", "Niveles"))
        previous = 0.0
        seen_stories = set()
        for index, story in enumerate(self.stories, start=1):
            name = str(story.get("name", "")).strip()
            height = to_float(story.get("height"), 0.0)
            elevation = to_float(story.get("elevation"), 0.0)
            if not name:
                issues.append(Issue("error", "Nivel sin nombre.", "Niveles", f"#{index}"))
            elif name in seen_stories:
                issues.append(Issue("error", f"Nombre de nivel repetido: {name}.", "Niveles"))
            seen_stories.add(name)
            if height <= 0:
                issues.append(Issue("error", f"El nivel {name or index} tiene altura no positiva.", "Niveles"))
            if elevation <= previous:
                issues.append(Issue("error", f"La elevación de {name or index} debe ser mayor que la anterior.", "Niveles"))
            previous = elevation
        for axis, grids in (("X", self.grid_x), ("Y", self.grid_y)):
            if not grids:
                issues.append(Issue("error", f"No hay grillas en {axis}.", "Grillas"))
                continue
            ids = [str(g.get("id", "")).strip() for g in grids]
            if any(not i for i in ids):
                issues.append(Issue("error", f"Hay grillas {axis} sin ID.", "Grillas"))
            repeated = sorted({i for i in ids if ids.count(i) > 1 and i})
            if repeated:
                issues.append(Issue("error", f"IDs de grilla {axis} repetidos: {', '.join(repeated)}.", "Grillas"))
            coords = [to_float(g.get("coord"), float("nan")) for g in grids]
            if any(math.isnan(c) for c in coords):
                issues.append(Issue("error", f"Coordenadas de grilla {axis} no numéricas.", "Grillas"))
            elif any(coords[i] >= coords[i + 1] for i in range(len(coords) - 1)):
                issues.append(Issue("warning", f"Las coordenadas {axis} no están en orden creciente.", "Grillas"))
            if len(grids) < 2:
                issues.append(Issue("warning", f"Se requieren al menos dos grillas {axis} para formar vanos.", "Grillas"))
        inclined_ids = [str(i.get("id", "")).strip() for i in self.inclined_x + self.inclined_y]
        repeated = sorted({i for i in inclined_ids if inclined_ids.count(i) > 1 and i})
        if repeated:
            issues.append(Issue("error", f"IDs de grilla inclinada repetidos: {', '.join(repeated)}.", "Grillas"))
        for item in self.inclined_x + self.inclined_y:
            if abs(to_float(item.get("start")) - to_float(item.get("end"))) < 1e-9:
                issues.append(Issue("warning", f"La grilla inclinada {item.get('id', '')} es vertical/horizontal o nula.", "Grillas"))
        material_names = {m["name"] for m in self.materials}
        section_names = {s["name"] for s in self.frame_sections}
        repeated_sections = sorted({s["name"] for s in self.frame_sections
                                    if [x["name"] for x in self.frame_sections].count(s["name"]) > 1})
        if repeated_sections:
            issues.append(Issue("error", f"Secciones repetidas: {', '.join(repeated_sections)}.", "Secciones"))
        for section in self.frame_sections:
            name = section.get("name", "")
            if section.get("material") not in material_names:
                issues.append(Issue("error", f"La sección {name} usa un material inexistente: {section.get('material')}.", "Secciones"))
            if to_float(section.get("d")) <= 0 or to_float(section.get("bf")) <= 0:
                issues.append(Issue("error", f"La sección {name} tiene dimensiones no positivas.", "Secciones"))
        if not self.slabs:
            issues.append(Issue("error", "No hay secciones de losa.", "Losas y muros"))
        if not self.walls:
            issues.append(Issue("error", "No hay secciones de muro.", "Losas y muros"))
        for item in self.slabs + self.walls:
            if item.get("material") not in material_names:
                issues.append(Issue("error", f"{item.get('name')} usa un material inexistente: {item.get('material')}.", "Losas y muros"))
            if to_float(item.get("thickness")) <= 0:
                issues.append(Issue("error", f"{item.get('name')} tiene espesor no positivo.", "Losas y muros"))
        used_columns = set()
        for wall in self.plan.walls:
            if not wall.col_a and not wall.col_b:
                continue  # fila de inicio vacía
            if wall.col_a not in {c.id for c in self.plan.columns}:
                issues.append(Issue("warning", f"Muro {wall.id}: columna A '{wall.col_a}' no existe.", "Planta"))
            if wall.col_b not in {c.id for c in self.plan.columns}:
                issues.append(Issue("warning", f"Muro {wall.id}: columna B '{wall.col_b}' no existe.", "Planta"))
            if wall.length <= 1e-9:
                issues.append(Issue("warning", f"Muro {wall.id} tiene longitud nula.", "Planta"))
            used_columns.add((wall.col_a, wall.col_b))
        for section in self.frame_sections:
            if section["name"] not in section_names:
                continue
        for column in self.plan.columns:
            if column.section and column.section not in section_names:
                issues.append(Issue("warning", f"Columna {column.id} usa sección inexistente: {column.section}.", "Planta"))
        for beam in self.plan.beams:
            if beam.section and beam.section not in section_names:
                issues.append(Issue("warning", f"Viga {beam.id} usa sección inexistente: {beam.section}.", "Planta"))
        wall_names = {w["name"] for w in self.walls}
        slab_names = {s["name"] for s in self.slabs}
        for slab in self.plan.slabs:
            if slab.section not in slab_names and slab.section != "VACIO":
                issues.append(Issue("warning", f"Losa {slab.id} usa sección inexistente: {slab.section}.", "Planta"))
        for wall in self.plan.walls:
            if wall.section and wall.section not in wall_names:
                issues.append(Issue("warning", f"Muro {wall.id} usa sección inexistente: {wall.section}.", "Planta"))
        pattern_names = set(self.all_pattern_names())
        seen_combos = set()
        for combo in self.combos:
            name = str(combo.get("name", "")).strip()
            if not name:
                issues.append(Issue("error", "Combinación sin nombre.", "Cargas"))
            if name in seen_combos:
                issues.append(Issue("error", f"Combinación repetida: {name}.", "Cargas"))
            seen_combos.add(name)
            if combo.get("type") == "Envelope":
                if not any(c.get("type") == "Linear Add" for c in self.combos):
                    issues.append(Issue("warning", f"La envolvente {name} no tiene combinaciones lineales.", "Cargas"))
                continue
            for case_name in combo.get("factors", {}):
                if case_name not in pattern_names:
                    issues.append(Issue("error", f"La combinación {name} usa un patrón inexistente: {case_name}.", "Cargas"))
        return issues

    # -- persistencia -----------------------------------------------------
    def to_dict(self) -> dict:
        data = {key: copy.deepcopy(value) for key, value in self.__dict__.items()
                if key not in ("plan", "path", "dirty")}
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        p = cls()
        for key, value in (data or {}).items():
            if key in ("plan", "path", "dirty"):
                continue
            if hasattr(p, key):
                setattr(p, key, copy.deepcopy(value))
        p.assignments.setdefault("column_sections", {})
        p.assignments.setdefault("beam_sections", {})
        p.assignments.setdefault("slab_sections", {})
        p.assignments.setdefault("wall_defs", [])
        if not p.assignments["wall_defs"]:
            p.assignments["wall_defs"] = _starter_walls(p)
        if not p.stories:
            p.stories = _build_stories(1, 3.0, 3.0)
        p.generate_frame_sections()
        p.generate_plan()
        p.dirty = False
        return p

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format": "etabs-cixtop-project", "version": template.APP_VERSION,
                   "project": self.to_dict()}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.path = path
        self.dirty = False
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = payload.get("project", payload)
        project = cls.from_dict(data)
        project.path = path
        return project

    # -- importación opcional desde Excel ---------------------------------
    @classmethod
    def import_workbook(cls, path: str | Path) -> "Project":
        """Importa valores de un libro CIXTOP evitando sobrescribir lo no leído.

        Es una ayuda de migración, no una dependencia: si openpyxl no está
        instalado o el libro no tiene la estructura esperada se lanza un error
        claro.
        """
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover - entorno sin openpyxl
            raise RuntimeError("Para importar un libro instala openpyxl (py -m pip install openpyxl).") from exc
        path = Path(path)
        wb = openpyxl.load_workbook(path, data_only=False, keep_vba=True)
        if "PROYECTO" not in wb.sheetnames:
            raise ValueError("El libro no contiene la hoja PROYECTO.")
        ws = wb["PROYECTO"]
        project = cls.new()
        project.name = str(ws["K8"].value or project.name)
        project.description = str(ws["K9"].value or project.description)
        count = to_int(ws["G13"].value, 0)
        typical = to_float(ws["G14"].value, 3.0)
        first = to_float(ws["G15"].value, typical)
        if count > 0:
            project.generate_stories(count, typical, first)
        x_coords = _read_grid_coords(ws, 11, 13, 20, 69)
        y_coords = _read_grid_coords(ws, 19, 21, 20, 69)
        if x_coords:
            project.grid_x = _build_grids("X", x_coords)
        if y_coords:
            project.grid_y = _build_grids("Y", y_coords)
        inclined_x = []
        for row in range(20, 70):
            gid, start, end = ws.cell(row, 28).value, ws.cell(row, 29).value, ws.cell(row, 30).value
            if gid and start is not None and end is not None:
                inclined_x.append({"id": str(gid), "start": to_float(start), "end": to_float(end)})
        if inclined_x:
            project.inclined_x = inclined_x
        inclined_y = []
        for row in range(20, 70):
            gid, start, end = ws.cell(row, 32).value, ws.cell(row, 33).value, ws.cell(row, 34).value
            if gid and start is not None and end is not None:
                inclined_y.append({"id": str(gid), "start": to_float(start), "end": to_float(end)})
        project.inclined_y = inclined_y
        # Materiales
        materials = []
        for row in range(76, 109):
            name = ws.cell(row, 3).value
            kind = str(ws.cell(row, 6).value or "").strip()
            if not name or kind not in ("Concrete", "Rebar", "Tendon", "Steel", "Masonry"):
                continue
            materials.append({
                "name": str(name), "kind": kind,
                "fc": to_float(ws.cell(row, 8).value),
                "fy": to_float(ws.cell(row, 10).value),
                "fm": to_float(ws.cell(row, 12).value),
                "E": to_float(ws.cell(row, 14).value),
                "weight": to_float(ws.cell(row, 16).value),
                "poisson": to_float(ws.cell(row, 18).value, 0.2),
            })
        if materials:
            project.materials = materials
        # Secciones de viga/columna
        sections = []
        for row in range(122, 199):
            name = ws.cell(row, 3).value
            if not name:
                continue
            geometry = str(ws.cell(row, 11).value or "")
            d = to_float(ws.cell(row, 13).value)
            bf = to_float(ws.cell(row, 14).value)
            tw = to_float(ws.cell(row, 15).value)
            tf = to_float(ws.cell(row, 16).value)
            area, inertia = template.section_properties(geometry, d, bf, tw, tf)
            sections.append({
                "name": str(name), "material": str(ws.cell(row, 6).value or ""),
                "element": str(ws.cell(row, 9).value or ""), "geometry": geometry,
                "d": d, "bf": bf, "tw": tw, "tf": tf,
                "f22": to_float(ws.cell(row, 17).value, 1.0),
                "f33": to_float(ws.cell(row, 18).value, 1.0),
                "area": area, "inertia": inertia, "rebar_cover": 4.0,
            })
        if sections:
            project.frame_sections = sections
            project.section_counts = {key: 0 for key in project.section_counts}
            counts: dict[str, int] = {}
            for section in sections:
                prefix = str(section["name"]).rsplit("_", 1)[0]
                counts[prefix] = counts.get(prefix, 0) + 1
            for group in template.DEFAULT_SECTION_GROUPS:
                if group["prefix"] in counts:
                    project.section_counts[group["count_key"]] = counts[group["prefix"]]
        # Losas / muros
        slabs = []
        for row in range(211, 214):
            name = ws.cell(row, 3).value
            if not name:
                continue
            slabs.append({
                "name": str(name), "material": str(ws.cell(row, 5).value or ""),
                "model_type": str(ws.cell(row, 7).value or "Shell-Thin"),
                "slab_type": str(ws.cell(row, 9).value or "Slab"),
                "thickness": to_float(ws.cell(row, 11).value, 20),
                "carpet": to_float(ws.cell(row, 13).value),
                "rib_top": to_float(ws.cell(row, 15).value),
                "rib_bottom": to_float(ws.cell(row, 17).value),
                "spacing_1": to_float(ws.cell(row, 19).value),
                "spacing_2": to_float(ws.cell(row, 21).value),
                "mods": [1.0] * 7,
            })
        walls = []
        for row in range(220, 230):
            name = ws.cell(row, 3).value
            if not name:
                continue
            walls.append({
                "name": str(name), "material": str(ws.cell(row, 5).value or ""),
                "model_type": str(ws.cell(row, 7).value or "Shell-Thick"),
                "thickness": to_float(ws.cell(row, 9).value, 20),
                "mods": [to_float(ws.cell(row, col).value, 1.0)
                         for col in (11, 13, 15, 17, 19, 21, 23)],
            })
        if slabs:
            project.slabs = slabs
        if walls:
            project.walls = walls
        # Cargas
        patterns = []
        for row in list(range(329, 332)) + [348, 349]:
            name = ws.cell(row, 4).value
            if not name:
                continue
            patterns.append({
                "name": str(name), "type": str(ws.cell(row, 6).value or "Dead"),
                "self_weight": to_float(ws.cell(row, 8).value) if row < 340 else 0.0,
                "description": str(ws.cell(row, 10).value or ws.cell(row, 14).value or ""),
                "direction": str(ws.cell(row, 8).value or "X") if row >= 340 else "",
            })
        if patterns:
            project.patterns = [p for p in patterns if p["type"].lower() != "quake"]
            project.seismic["patterns"] = [
                {"name": p["name"], "type": "Quake",
                 "direction": p.get("direction", "X"), "lateral": "User Coefficient"}
                for p in patterns if p["type"].lower() == "quake"]
        seismic = project.seismic
        for key, cell in (("Z", "I335"), ("U", "I336"), ("S", "I337"),
                          ("Tp", "I338"), ("TL", "I339"), ("R", "I340"),
                          ("T", "I341"), ("eccentricity", "I345")):
            seismic[key] = to_float(ws[cell].value, seismic.get(key, 0))
        combos = []
        for row in range(360, 370):
            name = ws.cell(row, 4).value
            if not name:
                continue
            factors = {}
            for col, case_name in zip(range(9, 14),
                                      [str(ws.cell(359, c).value or "") for c in range(9, 14)]):
                factor = to_float(ws.cell(row, col).value)
                if factor and case_name:
                    factors[case_name] = factor
            combos.append({"name": str(name), "type": str(ws.cell(row, 7).value or "Linear Add"),
                           "factors": factors, "notes": str(ws.cell(row, 14).value or "")})
        if combos:
            project.combos = combos
        project.generate_frame_sections()
        project.generate_plan()
        project.dirty = True
        return project


# --------------------------------------------------------------------------
# Constructores auxiliares
# --------------------------------------------------------------------------

def _build_stories(count: int, typical: float, first: float) -> list[dict]:
    stories = []
    elevation = 0.0
    for index in range(1, count + 1):
        height = first if index == 1 else typical
        elevation += height
        stories.append({"name": f"Piso {index}", "height": float(height),
                        "elevation": float(elevation)})
    return stories


def _starter_walls(project: "Project") -> list[dict]:
    section = project.walls[0]["name"] if project.walls else ""
    return [{"id": f"M-{index:03d}", "a": "", "b": "", "section": section}
            for index in range(1, 21)]


def _build_grids(axis: str, coords: list[float]) -> list[dict]:
    grids = []
    for index, coord in enumerate(coords, start=1):
        grid_id = column_letter(index) if axis == "X" else str(index)
        grids.append({"id": grid_id, "coord": float(coord), "spacing": 0.0})
    for index, grid in enumerate(grids[:-1]):
        grid["spacing"] = float(grids[index + 1]["coord"]) - float(grid["coord"])
    return grids


def _read_grid_coords(ws, id_col: int, value_col: int, start: int, end: int) -> list[float]:
    coords = []
    for row in range(start, end + 1):
        if ws.cell(row, id_col).value in (None, ""):
            if coords:
                break
            continue
        coords.append(to_float(ws.cell(row, value_col).value))
    return coords
