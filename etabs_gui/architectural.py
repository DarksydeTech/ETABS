"""Análisis geométrico de continuidad entre plantas a partir de archivos DXF.

El módulo identifica segmentos lineales de capas arquitectónicas y compara su
posición geométrica entre niveles. No interpreta por sí solo la función
estructural de un elemento: los resultados son candidatos para revisión.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Segment:
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float
    entity_type: str = "LINE"

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


@dataclass
class FloorDrawing:
    name: str
    source: str
    segments: list[Segment] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    units: str = "drawing units"
    ignored_entities: int = 0


@dataclass(frozen=True)
class ContinuityMatch:
    upper_index: int
    lower_index: int
    status: str
    overlap_ratio: float
    offset: float
    angle_difference: float
    side: str = "upper"



LAYER_CATEGORY_DEFAULTS = {
    "muros": "wall", "muros-bajos": "low_wall", "wall": "wall",
    "columnas": "column", "vigas vp": "primary_beam",
    "vigas vs": "secondary_beam", "escalera": "stair",
    "proyecciones": "projection", "planta": "plan_boundary",
    "plantas1": "plan_boundary", "plants": "plan_boundary",
    "casco": "plan_boundary", "a-trazo": "reference",
    "achurado": "hatch", "textura": "hatch", "cotas": "annotation",
    "a-textos": "annotation", "a-textos2": "annotation",
    "a-titulos": "annotation", "texto-1": "annotation",
    "textos2": "annotation", "textos4": "annotation",
    "muebles": "furniture", "a_mueble": "furniture",
    "puerta": "opening", "puertas": "opening",
    "puertas-ventanas": "opening", "ventana": "opening", "vano": "opening",
    "sanitarios": "equipment", "lavaderos": "equipment",
    "electrodomesticos": "equipment", "est-fierros": "detail",
    "nivel": "reference", "marco": "reference", "membrete": "reference",
    "defpoints": "reference",
}
CATEGORY_LABELS = {
    "wall": "Muro", "low_wall": "Muro bajo / parapeto",
    "column": "Columna", "primary_beam": "Viga principal",
    "secondary_beam": "Viga secundaria", "stair": "Escalera",
    "projection": "Proyección", "plan_boundary": "Límite de planta / área",
    "reference": "Referencia / auxiliar", "hatch": "Achurado",
    "annotation": "Texto / cota", "furniture": "Mobiliario",
    "opening": "Puerta / ventana / vano", "equipment": "Equipamiento",
    "detail": "Detalle", "unknown": "Sin clasificar",
}
EXCLUDED_CATEGORIES = {"projection", "plan_boundary", "reference", "hatch",
                       "annotation", "furniture", "opening", "equipment", "detail"}
COMPARABLE_CATEGORIES = {"wall", "low_wall", "column", "primary_beam",
                         "secondary_beam", "stair"}


def default_layer_category(layer: str) -> str:
    return LAYER_CATEGORY_DEFAULTS.get(str(layer).strip().casefold(), "unknown")


def _distance_point_line(px: float, py: float, ax: float, ay: float,
                         ux: float, uy: float) -> float:
    return abs((px - ax) * uy - (py - ay) * ux)


def _segment_projection(segment: Segment, ox: float, oy: float,
                        ux: float, uy: float) -> tuple[float, float]:
    a = (segment.x1 - ox) * ux + (segment.y1 - oy) * uy
    b = (segment.x2 - ox) * ux + (segment.y2 - oy) * uy
    return min(a, b), max(a, b)


def _angle_difference(a: Segment, b: Segment) -> float:
    aa = math.atan2(a.y2 - a.y1, a.x2 - a.x1)
    bb = math.atan2(b.y2 - b.y1, b.x2 - b.x1)
    delta = abs((aa - bb + math.pi / 2) % math.pi - math.pi / 2)
    return math.degrees(delta)


def compare_segments(a: Segment, b: Segment, tolerance: float = 0.15,
                     angle_tolerance: float = 5.0) -> tuple[float, float, float]:
    """Return overlap ratio, perpendicular offset and angular difference."""
    if a.length <= 1e-9 or b.length <= 1e-9:
        return 0.0, math.inf, 180.0
    angle = _angle_difference(a, b)
    ux = (a.x2 - a.x1) / a.length
    uy = (a.y2 - a.y1) / a.length
    offset = (_distance_point_line(b.x1, b.y1, a.x1, a.y1, ux, uy) +
              _distance_point_line(b.x2, b.y2, a.x1, a.y1, ux, uy)) / 2
    if angle > angle_tolerance or offset > tolerance:
        return 0.0, offset, angle
    a0, a1 = _segment_projection(a, a.x1, a.y1, ux, uy)
    b0, b1 = _segment_projection(b, a.x1, a.y1, ux, uy)
    overlap = max(0.0, min(a1, b1) - max(a0, b0))
    ratio = overlap / max(max(a.length, b.length), 1e-9)
    return min(1.0, ratio), offset, angle


def _segment_coverage(target: Segment, candidates: list[Segment],
                      tolerance: float, angle_tolerance: float) -> tuple[float, int, float, float]:
    """Fraction of target length covered by the union of collinear candidates."""
    if target.length <= 1e-9:
        return 0.0, -1, math.inf, 180.0
    ux = (target.x2 - target.x1) / target.length
    uy = (target.y2 - target.y1) / target.length
    intervals: list[tuple[float, float]] = []
    best_index, best_offset, best_angle, best_overlap = -1, math.inf, 180.0, 0.0
    for index, candidate in enumerate(candidates):
        if candidate.length <= 1e-9:
            continue
        angle = _angle_difference(target, candidate)
        offset = (_distance_point_line(candidate.x1, candidate.y1, target.x1, target.y1, ux, uy) +
                  _distance_point_line(candidate.x2, candidate.y2, target.x1, target.y1, ux, uy)) / 2
        if angle > angle_tolerance or offset > tolerance:
            continue
        p0, p1 = _segment_projection(candidate, target.x1, target.y1, ux, uy)
        lo, hi = max(0.0, p0), min(target.length, p1)
        overlap = max(0.0, hi - lo)
        if overlap <= 1e-9:
            continue
        intervals.append((lo, hi))
        if overlap > best_overlap:
            best_index, best_offset, best_angle, best_overlap = index, offset, angle, overlap
    if not intervals:
        return 0.0, -1, math.inf, 180.0
    intervals.sort()
    covered = 0.0
    current_start, current_end = intervals[0]
    for lo, hi in intervals[1:]:
        if lo <= current_end:
            current_end = max(current_end, hi)
        else:
            covered += current_end - current_start
            current_start, current_end = lo, hi
    covered += current_end - current_start
    return min(1.0, covered / target.length), best_index, best_offset, best_angle



def compare_floors(lower: FloorDrawing, upper: FloorDrawing,
                   tolerance: float = 0.15, angle_tolerance: float = 5.0,
                   full_ratio: float = 0.85,
                   layer_categories: dict[str, str] | None = None) -> list[ContinuityMatch]:
    """Compare geometry only within compatible semantic DXF layer categories."""
    categories = layer_categories or {}

    def category(segment: Segment) -> str:
        return categories.get(segment.layer, default_layer_category(segment.layer))

    def has_geometric_overlap(target: Segment, candidates: list[Segment]) -> bool:
        return _segment_coverage(target, candidates, tolerance, angle_tolerance)[0] > 1e-9

    results: list[ContinuityMatch] = []
    for ui, segment in enumerate(upper.segments):
        cat = category(segment)
        if cat in EXCLUDED_CATEGORIES:
            results.append(ContinuityMatch(ui, -1, "excluded", 0.0, math.inf, 180.0, "upper"))
            continue
        if cat not in COMPARABLE_CATEGORIES:
            results.append(ContinuityMatch(ui, -1, "review", 0.0, math.inf, 180.0, "upper"))
            continue
        compatible = [(i, item) for i, item in enumerate(lower.segments)
                      if category(item) == cat]
        ratio, local_i, offset, angle = _segment_coverage(
            segment, [item for _, item in compatible], tolerance, angle_tolerance)
        if ratio >= full_ratio:
            status = "continuous"
        elif ratio > 1e-9:
            status = "partial"
        elif has_geometric_overlap(segment, [item for item in lower.segments
                                             if category(item) in COMPARABLE_CATEGORIES and category(item) != cat]):
            status = "review"
        else:
            status = "appears"
        li = compatible[local_i][0] if local_i >= 0 else -1
        results.append(ContinuityMatch(ui, li, status, ratio, offset, angle, "upper"))

    for li, segment in enumerate(lower.segments):
        cat = category(segment)
        if cat in EXCLUDED_CATEGORIES:
            results.append(ContinuityMatch(-1, li, "excluded", 0.0, math.inf, 180.0, "lower"))
            continue
        if cat not in COMPARABLE_CATEGORIES:
            results.append(ContinuityMatch(-1, li, "review", 0.0, math.inf, 180.0, "lower"))
            continue
        compatible = [(i, item) for i, item in enumerate(upper.segments)
                      if category(item) == cat]
        ratio, local_i, offset, angle = _segment_coverage(
            segment, [item for _, item in compatible], tolerance, angle_tolerance)
        if ratio >= full_ratio:
            status = "continuous"
        elif ratio > 1e-9:
            status = "partial"
        elif has_geometric_overlap(segment, [item for item in upper.segments
                                             if category(item) in COMPARABLE_CATEGORIES and category(item) != cat]):
            status = "review"
        else:
            status = "disappears"
        ui = compatible[local_i][0] if local_i >= 0 else -1
        results.append(ContinuityMatch(ui, li, status, ratio, offset, angle, "lower"))
    return results

def read_dxf(path: str | Path, level_name: str, chord_error: float = 0.10,
             include_layers: Iterable[str] | None = None) -> FloorDrawing:
    """Read common DXF geometry using ezdxf; coordinates remain in drawing units."""
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError("Falta ezdxf. Instálalo con: py -m pip install ezdxf") from exc

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    try:
        document = ezdxf.readfile(source)
        modelspace = document.modelspace()
    except Exception as exc:
        raise RuntimeError(f"No se pudo leer el DXF '{source.name}': {exc}") from exc

    selected = {str(name).casefold() for name in include_layers} if include_layers else None

    def auxiliary_layer(name: str) -> bool:
        normalized = name.casefold().replace("_", "-").replace(" ", "-")
        tokens = ("dim", "cota", "text", "annot", "mueble", "mobili",
                  "furn", "hatch", "relleno", "trama", "puerta-mob")
        return any(token in normalized for token in tokens)
    segments: list[Segment] = []
    layers: set[str] = set()
    ignored = 0

    def add_line(layer: str, start, end, entity_type: str) -> None:
        x1, y1 = float(start[0]), float(start[1])
        x2, y2 = float(end[0]), float(end[1])
        if math.hypot(x2 - x1, y2 - y1) > 1e-6:
            segments.append(Segment(layer, x1, y1, x2, y2, entity_type))

    def consume(entity, depth: int = 0) -> None:
        nonlocal ignored
        if depth > 5:
            ignored += 1
            return
        kind = entity.dxftype()
        layer = str(entity.dxf.get("layer", "0"))
        layers.add(layer)
        if (selected is not None and layer.casefold() not in selected) or (selected is None and auxiliary_layer(layer)):
            ignored += 1
            return
        try:
            if kind == "LINE":
                add_line(layer, entity.dxf.start, entity.dxf.end, kind)
            elif kind == "LWPOLYLINE":
                points = list(entity.get_points("xy"))
                closed = bool(entity.closed)
                for i in range(max(0, len(points) - 1)):
                    add_line(layer, points[i], points[i + 1], kind)
                if closed and len(points) > 2:
                    add_line(layer, points[-1], points[0], kind)
            elif kind == "POLYLINE":
                points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                for i in range(max(0, len(points) - 1)):
                    add_line(layer, points[i], points[i + 1], kind)
                if entity.is_closed and len(points) > 2:
                    add_line(layer, points[-1], points[0], kind)
            elif kind in ("ARC", "CIRCLE"):
                if kind == "CIRCLE":
                    center = entity.dxf.center
                    radius = float(entity.dxf.radius)
                    start_angle, end_angle = 0.0, 360.0
                else:
                    center = entity.dxf.center
                    radius = float(entity.dxf.radius)
                    start_angle = float(entity.dxf.start_angle)
                    end_angle = float(entity.dxf.end_angle)
                    while end_angle <= start_angle:
                        end_angle += 360.0
                sweep = math.radians(end_angle - start_angle)
                if radius <= 0:
                    return
                # Chord count limits sagitta to the requested drawing-unit error.
                if chord_error <= 0:
                    count = 48
                else:
                    step = 2 * math.acos(max(-1.0, min(1.0, 1 - chord_error / radius)))
                    count = max(4, min(720, int(math.ceil(sweep / max(step, 0.02)))))
                pts = []
                for i in range(count + 1):
                    angle = math.radians(start_angle) + sweep * i / count
                    pts.append((center.x + radius * math.cos(angle),
                                center.y + radius * math.sin(angle)))
                for a, b in zip(pts, pts[1:]):
                    add_line(layer, a, b, kind)
            elif kind == "INSERT":
                for virtual in entity.virtual_entities():
                    consume(virtual, depth + 1)
            else:
                ignored += 1
        except Exception:
            ignored += 1

    for entity in modelspace:
        consume(entity)
    return FloorDrawing(str(level_name).strip() or source.stem, str(source),
                        segments, sorted(layers), str(document.header.get("$INSUNITS", 0)),
                        ignored)


def alignment_offsets_by_bounds(drawings: list[FloorDrawing]) -> list[tuple[float, float]]:
    """Calculate translations using each drawing's bounding-box center.

    Unlike a vertex-average centroid, the bounding-box center is invariant to
    whether the same geometry is encoded as one polyline or many segments.
    The first drawing is the fixed reference and is never translated.
    """
    if not drawings:
        return []

    centers: list[tuple[float, float]] = []
    for drawing in drawings:
        points = [(coordinate, ordinate)
                  for segment in drawing.segments
                  for coordinate, ordinate in ((segment.x1, segment.y1),
                                               (segment.x2, segment.y2))]
        if not points:
            centers.append((0.0, 0.0))
            continue
        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)
        centers.append(((min_x + max_x) / 2, (min_y + max_y) / 2))

    reference_x, reference_y = centers[0]
    return [(reference_x - center_x, reference_y - center_y)
            for center_x, center_y in centers]


def apply_alignment_offsets(drawings: list[FloorDrawing],
                            offsets: list[tuple[float, float]]) -> None:
    """Apply previously reviewed translations to drawings in place."""
    if len(drawings) != len(offsets):
        raise ValueError("La cantidad de desplazamientos no coincide con los niveles.")
    for drawing, (dx, dy) in zip(drawings, offsets):
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            continue
        drawing.segments = [
            Segment(s.layer, s.x1 + dx, s.y1 + dy,
                    s.x2 + dx, s.y2 + dy, s.entity_type)
            for s in drawing.segments
        ]


def align_by_centroid(drawings: list[FloorDrawing]) -> None:
    """Compatibility wrapper: align by bounding-box center, not vertex centroid."""
    apply_alignment_offsets(drawings, alignment_offsets_by_bounds(drawings))
