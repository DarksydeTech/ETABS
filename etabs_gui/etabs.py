"""Puente COM con ETABS (Windows + CSI ETABS API).

Usa ``comtypes`` porque el API de ETABS 22 expone interfaces duales cuyo
``IDispatch`` falla con ``pywin32`` (error E_NOINTERFACE al pedir ``SapModel``).
Trabaja sobre ``model.Project``; no lee Excel.
"""
from __future__ import annotations

import math
from typing import Any

from .model import Project, to_float
from .template import seismic_coefficient, seismic_k

UNITS_TON_M = 12      # Tonf, m, C
UNITS_KGF_CM = 14     # kgf, cm, C


def _system_decimal() -> str:
    """Separador decimal de Windows (ETABS importa tablas con la configuración regional)."""
    try:
        import ctypes
        buffer = ctypes.create_unicode_buffer(16)
        if ctypes.windll.kernel32.GetLocaleInfoW(0x0400, 0x0E, buffer, 16):
            return buffer.value or "."
    except Exception:  # noqa: BLE001
        pass
    return "."


DECIMAL = _system_decimal()

MAT_TYPES = {"concrete": 2, "rebar": 6, "tendon": 3, "steel": 1, "masonry": 7}
PATTERN_TYPES = {
    "DEAD": 1, "SUPERDEAD": 2, "LIVE": 3, "REDUCELIVE": 4, "QUAKE": 5,
    "SEISMIC": 5, "WIND": 6, "SNOW": 7, "OTHER": 8, "ROOFLIVE": 11,
}
SHELL_TYPES = {"Shell-Thin": 1, "Shell-Thick": 2, "Membrane": 3, "Layered": 6}
SLAB_TYPES = {"Slab": 0, "Drop": 1, "Stiff": 2, "Ribbed": 3,
              "Waffle": 4, "Mat": 5, "Footing": 6}
REBAR_MATERIAL = "Rebar ASTM A615 Gr 60"


def _ret(result: Any) -> int:
    """Código de retorno de comtypes: último entero de la tupla."""
    if isinstance(result, (tuple, list)):
        if not result:
            return 0
        last = result[-1]
        return int(last) if isinstance(last, (int, float, bool)) else 0
    return int(result) if isinstance(result, (int, float)) else 0


def _names(result: Any) -> list[str]:
    """Nombres devueltos por GetNameList: [count, (names...), ret]."""
    if isinstance(result, (tuple, list)):
        for item in result[1:]:
            if isinstance(item, (tuple, list)):
                return [str(x) for x in item]
    return []


def _num(value: Any) -> str:
    """Número para tablas de ETABS con el separador decimal del sistema."""
    text = f"{to_float(value):.6f}".rstrip("0").rstrip(".")
    if text in ("", "-0"):
        text = "0"
    return text.replace(".", DECIMAL)


class EtabsBridge:
    def __init__(self) -> None:
        self.application: Any = None
        self.model: Any = None
        self.log: list[str] = []

    # -- conexión ---------------------------------------------------------
    def connect(self, start_if_needed: bool = False) -> None:
        try:
            import comtypes.client
        except ImportError as exc:
            raise RuntimeError(
                "Falta comtypes. Instala los requisitos: py -m pip install comtypes") from exc
        application = None
        try:
            application = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        except Exception:  # noqa: BLE001
            application = None
        if application is None:
            helper = None
            last_error = None
            for progid in ("ETABSv1.Helper", "CSiAPIv1.Helper"):
                try:
                    helper = comtypes.client.CreateObject(progid)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            if helper is None:
                raise RuntimeError(
                    f"No se encontró la API COM de ETABS: {last_error}")
            try:
                import comtypes.gen.ETABSv1 as api
                helper = helper.QueryInterface(api.cHelper)
            except Exception:  # noqa: BLE001
                pass
            if start_if_needed:
                try:
                    application = helper.CreateObjectProgID(
                        "CSI.ETABS.API.ETABSObject")
                    application.ApplicationStart()
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"No se pudo iniciar ETABS: {exc}") from exc
            else:
                application = helper.GetObject("CSI.ETABS.API.ETABSObject")
        if application is None:
            raise RuntimeError(
                "ETABS no está abierto. Abre ETABS o usa 'Nuevo modelo ETABS'.")
        try:
            self.model = application.SapModel
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "ETABS respondió pero no entregó SapModel. Cierra ETABS y ábrelo "
                f"de nuevo. Detalle: {exc}") from exc
        self.application = application
        self._note("Conexión COM establecida.")

    def initialize_blank(self) -> None:
        if self.model is None:
            self.connect(start_if_needed=True)
        self.model.InitializeNewModel(UNITS_TON_M)
        self.model.File.NewBlank()
        self.model.SetPresentUnits(UNITS_TON_M)
        self._note("Modelo ETABS vacío creado (Ton, m, C).")

    def _require(self) -> Any:
        if self.model is None:
            raise RuntimeError("Conecta ETABS primero.")
        return self.model

    def _note(self, text: str) -> None:
        self.log.append(text)
        if len(self.log) > 500:
            self.log = self.log[-500:]

    # -- niveles ----------------------------------------------------------
    def export_stories(self, project: Project) -> int:
        model = self._require()
        stories = project.stories
        if not stories:
            raise RuntimeError("El proyecto no tiene niveles.")
        names = [str(s["name"]) for s in stories]
        heights = [to_float(s["height"]) for s in stories]
        count = len(stories)
        try:
            model.SetModelIsLocked(False)
        except Exception:  # noqa: BLE001
            pass
        result = model.Story.SetStories_2(
            0.0, count, names, heights,
            [True] * count, ["None"] * count, [False] * count,
            [0.0] * count, [0] * count)
        if _ret(result) != 0:
            raise RuntimeError(f"ETABS rechazó los niveles (código {_ret(result)}).")
        self._note(f"{count} niveles exportados.")
        return count

    # -- grillas ----------------------------------------------------------
    def export_grids(self, project: Project) -> int:
        """Crea el sistema G1 con líneas X, Y e inclinadas por DatabaseTables."""
        model = self._require()
        x = [(str(g["id"]), to_float(g["coord"])) for g in project.grid_x]
        y = [(str(g["id"]), to_float(g["coord"])) for g in project.grid_y]
        if not x and not y:
            raise RuntimeError("No hay grillas cartesianas.")
        if self._export_grids_tables(model, project, x, y):
            try:
                model.View.RefreshView(0, True)
            except Exception:  # noqa: BLE001
                pass
            return len(x) + len(y) + len(project.inclined_x) + len(project.inclined_y)
        self._note("DatabaseTables no disponible; solo se creó el origen G1.")
        try:
            model.GridSys.SetGridSys("G1", 0.0, 0.0, 0.0)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"No se pudo crear el sistema de grillas: {exc}") from exc
        return 0

    def _export_grids_tables(self, model, project, x, y) -> bool:
        try:
            dt = model.DatabaseTables
            if dt is None:
                return False
            general = self._table_get(dt, "Grid Definitions - General")
            lines = self._table_get(dt, "Grid Definitions - Grid Lines")
            if general is None or lines is None:
                return False
            gfields, grecords = general
            gindex = {name: i for i, name in enumerate(gfields)}
            existing = any(str(row[gindex.get("Name", 1)]).strip() == "G1"
                           for row in grecords)
            if not existing:
                grow = [""] * len(gfields)
                for key, value in (("Tower", "T1"), ("Name", "G1"),
                                   ("Type", "Cartesian"), ("Ux", "0"),
                                   ("Uy", "0"), ("Rz", "0"),
                                   ("StoryRange", "Default")):
                    if key in gindex:
                        grow[gindex[key]] = _num(value) if key in ("Ux", "Uy", "Rz") else value
                if not self._table_set(dt, "Grid Definitions - General",
                                       gfields, grecords + [grow]):
                    return False

            fields, records = lines
            index = {name: i for i, name in enumerate(fields)}
            keep = [row for row in records
                    if str(row[index.get("Name", 0)]).strip().upper() != "G1"]
            xmin = min(v for _, v in x) if x else 0.0
            xmax = max(v for _, v in x) if x else 0.0
            ymin = min(v for _, v in y) if y else 0.0
            ymax = max(v for _, v in y) if y else 0.0
            xmin_ext, xmax_ext = xmin, xmax
            ymin_ext, ymax_ext = ymin, ymax
            inclined: list[tuple[str, float, float, float, float]] = []
            for item in project.inclined_x:
                x1, y1, x2, y2 = _extend(to_float(item.get("start")), ymin,
                                         to_float(item.get("end")), ymax)
                xmin_ext, xmax_ext = min(xmin_ext, x1, x2), max(xmax_ext, x1, x2)
                ymin_ext, ymax_ext = min(ymin_ext, y1, y2), max(ymax_ext, y1, y2)
                inclined.append((str(item.get("id", "I")), x1, y1, x2, y2))
            for item in project.inclined_y:
                x1, y1, x2, y2 = _extend(xmin, to_float(item.get("start")),
                                         xmax, to_float(item.get("end")))
                xmin_ext, xmax_ext = min(xmin_ext, x1, x2), max(xmax_ext, x1, x2)
                ymin_ext, ymax_ext = min(ymin_ext, y1, y2), max(ymax_ext, y1, y2)
                inclined.append((str(item.get("id", "I")), x1, y1, x2, y2))
            # Con grillas inclinadas todas las líneas se escriben como "General"
            # con extremos explícitos: ETABS recorta las líneas X/Y al rectángulo
            # cartesiano y no las prolonga hasta la grilla inclinada.
            rows = []
            if inclined:
                for grid_id, coord in x:
                    rows.append(self._general_row(fields, index, grid_id,
                                                  coord, ymin_ext, coord, ymax_ext,
                                                  "End"))
                for grid_id, coord in y:
                    rows.append(self._general_row(fields, index, grid_id,
                                                  xmin_ext, coord, xmax_ext, coord,
                                                  "Start"))
                for grid_id, x1, y1, x2, y2 in inclined:
                    rows.append(self._general_row(fields, index, grid_id,
                                                  x1, y1, x2, y2, "Start"))
            else:
                for grid_id, coord in x:
                    rows.append(self._cartesian_row(fields, index, grid_id,
                                                    "X (Cartesian)", coord, "End"))
                for grid_id, coord in y:
                    rows.append(self._cartesian_row(fields, index, grid_id,
                                                    "Y (Cartesian)", coord, "Start"))
            if not self._table_set(dt, "Grid Definitions - Grid Lines",
                                   fields, keep + rows):
                return False
            self._note(f"Grillas exportadas: {len(x)} X, {len(y)} Y, "
                       f"{len(project.inclined_x) + len(project.inclined_y)} inclinadas.")
            return True
        except Exception as exc:  # noqa: BLE001
            self._note(f"Exportación de grillas por tablas falló: {exc}")
            return False

    def _general_row(self, fields, index, grid_id: str,
                     x1: float, y1: float, x2: float, y2: float,
                     bubble: str = "Start") -> list[str]:
        row = [""] * len(fields)
        row[index["Name"]] = "G1"
        row[index["LineType"]] = "General"
        row[index["ID"]] = str(grid_id)
        for key, value in (("X1", x1), ("Y1", y1), ("X2", x2), ("Y2", y2)):
            if key in index:
                row[index[key]] = _num(value)
        if "BubbleLoc" in index:
            row[index["BubbleLoc"]] = bubble
        if "Visible" in index:
            row[index["Visible"]] = "Yes"
        return row

    def _cartesian_row(self, fields, index, grid_id: str,
                       line_type: str, coord: float,
                       bubble: str) -> list[str]:
        row = [""] * len(fields)
        row[index["Name"]] = "G1"
        row[index["LineType"]] = line_type
        row[index["ID"]] = str(grid_id)
        row[index["Ordinate"]] = _num(coord)
        if "BubbleLoc" in index:
            row[index["BubbleLoc"]] = bubble
        if "Visible" in index:
            row[index["Visible"]] = "Yes"
        return row

    # -- materiales -------------------------------------------------------
    def export_materials(self, project: Project) -> int:
        model = self._require()
        model.SetModelIsLocked(False)
        model.SetPresentUnits(UNITS_KGF_CM)
        count = 0
        for material in project.materials:
            name = str(material.get("name", "")).strip()
            kind = str(material.get("kind", "")).strip().lower()
            if not name or kind not in MAT_TYPES:
                continue
            fc = to_float(material.get("fc"))
            fy = to_float(material.get("fy"))
            e_mod = to_float(material.get("E"))
            weight = to_float(material.get("weight")) * 0.001  # t/m³ -> kgf/cm³
            poisson = to_float(material.get("poisson"), 0.2)
            model.PropMaterial.SetMaterial(name, MAT_TYPES[kind])
            model.PropMaterial.SetMPIsotropic(name, e_mod, poisson, 0.00001)
            model.PropMaterial.SetWeightAndMass(name, 1, weight)
            if kind == "concrete":
                model.PropMaterial.SetOConcrete(name, fc, False, 0, 1, 2, 0.002, 0.005)
            elif kind == "rebar":
                model.PropMaterial.SetORebar(name, fy, fy * 1.25, fy, fy * 1.25,
                                             1, 2, 0.02, 0.1, False)
            elif kind == "tendon":
                model.PropMaterial.SetOTendon(name, fy, fy * 1.15, 1, 2)
            elif kind == "steel":
                fu = fy * 1.15
                model.PropMaterial.SetOSteel(name, fy, fu, fy * 1.1, fu * 1.1,
                                             1, 2, 0.02, 0.15, 0.2)
            count += 1
        model.SetPresentUnits(UNITS_TON_M)
        self._note(f"{count} materiales exportados.")
        return count

    def _ensure_rebar(self, project: Project) -> str:
        names = {m["name"] for m in project.materials}
        if REBAR_MATERIAL in names:
            return REBAR_MATERIAL
        for name in names:
            if name.lower().startswith("rebar"):
                return name
        return ""

    # -- secciones de barra ----------------------------------------------
    def export_sections(self, project: Project) -> int:
        model = self._require()
        model.SetPresentUnits(UNITS_TON_M)
        rebar = self._ensure_rebar(project)
        made = 0
        for section in project.frame_sections:
            name = str(section.get("name", "")).strip()
            material = str(section.get("material", "")).strip()
            geometry = str(section.get("geometry", "")).strip()
            if not name or not material:
                continue
            d = to_float(section.get("d")) / 100.0
            bf = to_float(section.get("bf")) / 100.0
            tw = to_float(section.get("tw")) / 100.0
            tf = to_float(section.get("tf")) / 100.0
            ret = -1
            if geometry == "Rectangular":
                ret = model.PropFrame.SetRectangle(name, material, d, bf)
            elif geometry == "Circular":
                ret = model.PropFrame.SetCircle(name, material, d)
            elif geometry == "Perfil_I":
                ret = model.PropFrame.SetISection(name, material, d, bf, tf, tw, bf, tf)
            elif geometry == "Tubo_Rectangular":
                ret = model.PropFrame.SetTube(name, material, d, bf, tf, tw)
            elif geometry == "Tubo_Circular":
                ret = model.PropFrame.SetPipe(name, material, d, tw)
            elif geometry == "Tipo_T":
                ret = model.PropFrame.SetTee(name, material, d, bf, tf, tw)
            elif geometry == "Tipo_L":
                ret = model.PropFrame.SetAngle(name, material, d, bf, tf, tw)
            if _ret(ret) != 0:
                self._note(f"ETABS rechazó la sección {name} (código {_ret(ret)}).")
                continue
            element = str(section.get("element", "")).lower()
            cover = to_float(section.get("rebar_cover"), 4.0) / 100.0
            if rebar and "concreto" in material.lower():
                try:
                    if element == "columna":
                        model.PropFrame.SetRebarColumn(
                            name, rebar, rebar, 1, 1, cover, 0, 3, 3,
                            "", "", 0.15, 2, 2, True)
                    else:
                        model.PropFrame.SetRebarBeam(
                            name, rebar, rebar, cover, cover, 0.0, 0.0, 0.0, 0.0)
                except Exception as exc:  # noqa: BLE001
                    self._note(f"Refuerzo no asignado en {name}: {exc}")
            modifiers = [1.0] * 8
            modifiers[4] = to_float(section.get("f22"), 1.0)   # I22
            modifiers[5] = to_float(section.get("f33"), 1.0)   # I33
            try:
                model.PropFrame.SetModifiers(name, modifiers)
            except Exception:  # noqa: BLE001
                pass
            made += 1
        model.View.RefreshView(0, True)
        self._note(f"{made} secciones de viga/columna exportadas.")
        return made

    # -- losas y muros ----------------------------------------------------
    def export_area_sections(self, project: Project) -> int:
        model = self._require()
        model.SetPresentUnits(UNITS_TON_M)
        made = 0
        for slab in project.slabs:
            name = str(slab.get("name", "")).strip()
            material = str(slab.get("material", "")).strip()
            if not name or not material:
                continue
            slab_type = SLAB_TYPES.get(str(slab.get("slab_type")), 0)
            shell = SHELL_TYPES.get(str(slab.get("model_type")), 1)
            thickness = to_float(slab.get("thickness"), 20.0) / 100.0
            ret = model.PropArea.SetSlab(name, slab_type, shell, material, thickness)
            if _ret(ret) != 0 and shell != 1:
                ret = model.PropArea.SetSlab(name, slab_type, 1, material, thickness)
            if _ret(ret) != 0:
                self._note(f"ETABS rechazó la losa {name}.")
                continue
            self._apply_area_modifiers(model, name, slab.get("mods", []))
            made += 1
        for wall in project.walls:
            name = str(wall.get("name", "")).strip()
            material = str(wall.get("material", "")).strip()
            if not name or not material:
                continue
            shell = SHELL_TYPES.get(str(wall.get("model_type")), 2)
            thickness = to_float(wall.get("thickness"), 20.0) / 100.0
            ret = model.PropArea.SetWall(name, 1, shell, material, thickness)
            if _ret(ret) != 0 and shell != 1:
                ret = model.PropArea.SetWall(name, 1, 1, material, thickness)
            if _ret(ret) != 0:
                self._note(f"ETABS rechazó el muro {name}.")
                continue
            self._apply_area_modifiers(model, name, wall.get("mods", []))
            made += 1
        model.View.RefreshView(0, True)
        self._note(f"{made} secciones de área exportadas.")
        return made

    def _apply_area_modifiers(self, model, name: str, values: list) -> None:
        modifiers = [1.0] * 10
        for index in range(min(7, len(values or []))):
            modifiers[index] = to_float(values[index], 1.0)
        if len(values or []) >= 7:
            modifiers[6] = modifiers[7] = to_float(values[6], 1.0)
        try:
            model.PropArea.SetModifiers(name, modifiers)
        except Exception:  # noqa: BLE001
            pass

    # -- cargas -----------------------------------------------------------
    def export_loads(self, project: Project) -> dict[str, int]:
        model = self._require()
        model.SetPresentUnits(UNITS_TON_M)
        patterns = 0
        for pattern in project.patterns:
            name = str(pattern.get("name", "")).strip()
            if not name:
                continue
            kind = PATTERN_TYPES.get(str(pattern.get("type", "Dead")).upper(), 8)
            weight = to_float(pattern.get("self_weight"))
            if _ret(model.LoadPatterns.Add(name, kind, weight, True)) != 0:
                try:
                    model.LoadPatterns.SetLoadType(name, kind)
                    model.LoadPatterns.SetSelfWTMultiplier(name, weight)
                except Exception as exc:  # noqa: BLE001
                    self._note(f"Patrón {name} no actualizado: {exc}")
                    continue
            patterns += 1
        for pattern in project.seismic.get("patterns", []):
            name = str(pattern.get("name", "")).strip()
            if not name:
                continue
            if _ret(model.LoadPatterns.Add(name, 5, 0.0, True)) != 0:
                try:
                    model.LoadPatterns.SetLoadType(name, 5)
                    model.LoadPatterns.SetSelfWTMultiplier(name, 0.0)
                except Exception:  # noqa: BLE001
                    continue
            patterns += 1
        self._apply_user_coefficient(model, project)
        combinations = 0
        linear: list[str] = []
        for combo in project.combos:
            name = str(combo.get("name", "")).strip()
            kind = str(combo.get("type", "Linear Add")).lower()
            if not name:
                continue
            try:
                model.RespCombo.Delete(name)
            except Exception:  # noqa: BLE001
                pass
            if kind == "envelope":
                model.RespCombo.Add(name, 1)
                for case in linear:
                    model.RespCombo.SetCaseList(name, 1, case, 1.0)
            else:
                model.RespCombo.Add(name, 0)
                for case, factor in combo.get("factors", {}).items():
                    if to_float(factor) != 0:
                        model.RespCombo.SetCaseList(name, 0, str(case), to_float(factor))
                linear.append(name)
            combinations += 1
        model.View.RefreshView(0, True)
        self._note(f"{patterns} patrones y {combinations} combinaciones exportadas.")
        return {"patterns": patterns, "combinations": combinations}

    def _apply_user_coefficient(self, model, project: Project) -> None:
        patterns = [p for p in project.seismic.get("patterns", [])]
        if not patterns:
            return
        coef = seismic_coefficient(project.seismic)
        k = seismic_k(project.seismic)
        ecc = to_float(project.seismic.get("eccentricity"), 0.05)
        try:
            dt = model.DatabaseTables
            data = self._table_get(dt, "Load Pattern Definitions - Auto Seismic - User Coefficient")
            if not data:
                return
            fields, records = data
            index = {name: i for i, name in enumerate(fields)}
            keep = [row for row in records
                    if str(row[index.get("Name", 0)]).strip()
                    not in {p["name"] for p in patterns}]
            for pattern in patterns:
                row = [""] * len(fields)
                row[index["Name"]] = pattern["name"]
                for key, value in {
                    "IsAuto": "Yes", "XDir": "Yes" if pattern.get("direction") == "X" else "No",
                    "YDir": "Yes" if pattern.get("direction") == "Y" else "No",
                    "EccRatio": _num(ecc), "C": _num(coef), "K": _num(k),
                }.items():
                    if key in index:
                        row[index[key]] = value
                keep.append(row)
            self._table_set(dt, "Load Pattern Definitions - Auto Seismic - User Coefficient",
                            fields, keep)
            self._note(f"Coeficiente sísmico ZUCS/R={coef:.4f}, K={k:.3f} aplicado.")
        except Exception as exc:  # noqa: BLE001
            self._note(f"No se pudo aplicar User Coefficient: {exc}")

    def _apply_mass_source(self, model, project: Project) -> None:
        self._note("La fuente de masa se define en ETABS (Define > Mass Source); "
                   "esta versión del API no expone SourceMass.")

    # -- planta -----------------------------------------------------------
    def export_plan(self, project: Project, clean_first: bool = False) -> dict[str, int]:
        model = self._require()
        plan = project.plan
        if not plan.columns:
            raise RuntimeError("La planta no tiene columnas. Revisa las grillas.")
        model.SetModelIsLocked(False)
        model.SetPresentUnits(UNITS_TON_M)
        self.export_stories(project)
        if clean_first:
            self._clean(model)
        elevations = [to_float(s["elevation"]) for s in project.stories]
        if not elevations:
            raise RuntimeError("No hay elevaciones de nivel.")
        points: dict[tuple[float, float, float], str] = {}

        def point(x: float, y: float, z: float) -> str:
            key = (round(x, 6), round(y, 6), round(z, 6))
            if key in points:
                return points[key]
            result = model.PointObj.AddCartesian(x, y, z, "", "", "Global", False, 0)
            name = _pick_name(result)
            if not name or _ret(result) != 0:
                raise RuntimeError(f"ETABS no creó el punto ({x:.3f}, {y:.3f}, {z:.3f}).")
            points[key] = name
            return name

        columns = {c.id: c for c in plan.columns}
        count_columns = count_beams = count_slabs = count_walls = 0
        for column in plan.columns:
            section = str(column.section or "").strip()
            if not section or section.upper() == "VACIO":
                continue
            base = point(column.x, column.y, 0.0)
            try:
                model.PointObj.SetRestraint(base, [True] * 6)
            except Exception:  # noqa: BLE001
                pass
            previous = base
            for elevation in elevations:
                current = point(column.x, column.y, elevation)
                result = model.FrameObj.AddByPoint(
                    previous, current, "", section, f"COL_{column.id}")
                frame = _pick_name(result)
                if frame and _ret(result) == 0:
                    if column.angle:
                        try:
                            model.FrameObj.SetLocalAxes(frame, float(column.angle))
                        except Exception:  # noqa: BLE001
                            pass
                    count_columns += 1
                previous = current
        for beam in plan.beams:
            section = str(beam.section or "").strip()
            if not section or section.upper() == "VACIO":
                continue
            left, right = columns.get(beam.col_a), columns.get(beam.col_b)
            if not left or not right:
                continue
            for elevation in elevations:
                p1 = point(left.x, left.y, elevation)
                p2 = point(right.x, right.y, elevation)
                result = model.FrameObj.AddByPoint(p1, p2, "", section, beam.id)
                if _pick_name(result) and _ret(result) == 0:
                    count_beams += 1
        for slab in plan.slabs:
            section = str(slab.section or "").strip()
            if not section or section.upper() == "VACIO" or len(slab.coords) < 3:
                continue
            for elevation in elevations:
                names = [point(x, y, elevation) for x, y in slab.coords]
                result = model.AreaObj.AddByPoint(len(names), names, "", section, slab.id)
                if _pick_name(result) and _ret(result) == 0:
                    count_slabs += 1
        for wall in plan.walls:
            section = str(wall.section or "").strip()
            if not section or section.upper() == "VACIO":
                continue
            left, right = columns.get(wall.col_a), columns.get(wall.col_b)
            if not left or not right:
                continue
            for index, elevation in enumerate(elevations):
                z0 = elevations[index - 1] if index else 0.0
                names = [point(left.x, left.y, z0), point(right.x, right.y, z0),
                         point(right.x, right.y, elevation), point(left.x, left.y, elevation)]
                result = model.AreaObj.AddByPoint(4, names, "", section, wall.id)
                if _pick_name(result) and _ret(result) == 0:
                    count_walls += 1
        try:
            model.View.RefreshView(0, True)
        except Exception:  # noqa: BLE001
            pass
        result = {"columns": count_columns, "beams": count_beams,
                  "slabs": count_slabs, "walls": count_walls}
        self._note("Planta exportada: " + ", ".join(f"{k} {v}" for k, v in result.items()))
        return result

    def _clean(self, model) -> None:
        for collection in (model.FrameObj, model.AreaObj):
            try:
                names = _names(collection.GetNameList())
                for name in names:
                    collection.Delete(name)
            except Exception:  # noqa: BLE001
                continue

    # -- tablas -----------------------------------------------------------
    @staticmethod
    def _table_get(dt, key: str):
        try:
            result = dt.GetTableForEditingArray(key, "")
        except Exception:
            return None
        if not isinstance(result, (tuple, list)) or len(result) < 5:
            return None
        fields = [str(x) for x in result[1]]
        if not fields:
            return None
        count = int(result[2])
        data = list(result[3])
        if _ret(result) != 0:
            return None
        rows = [data[i * len(fields):(i + 1) * len(fields)]
                for i in range(count)]
        return fields, [[str(value) for value in row] for row in rows]

    @staticmethod
    def _table_set(dt, key: str, fields, rows) -> bool:
        flat = [str(value) for row in rows for value in row]
        try:
            result = dt.SetTableForEditingArray(key, 0, list(fields), len(rows), flat)
            if _ret(result) != 0:
                return False
            applied = dt.ApplyEditedTables(True)
            return _ret(applied) == 0
        except Exception:
            try:
                dt.CancelTableEditing()
            except Exception:  # noqa: BLE001
                pass
            return False


def _extend(x1: float, y1: float, x2: float, y2: float, ext: float = 1.5):
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return x1, y1, x2, y2
    return (x1 - dx / length * ext, y1 - dy / length * ext,
            x2 + dx / length * ext, y2 + dy / length * ext)


def _pick_name(result: Any) -> str:
    if isinstance(result, (tuple, list)):
        for item in result:
            if isinstance(item, str) and item:
                return item
    return ""
