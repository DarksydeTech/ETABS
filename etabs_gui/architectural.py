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
    ratio = overlap / max(min(a.length, b.length), 1e-9)
    return min(1.0, ratio), offset, angle


def compare_floors(lower: FloorDrawing, upper: FloorDrawing,
                   tolerance: float = 0.15, angle_tolerance: float = 5.0,
                   full_ratio: float = 0.85) -> list[ContinuityMatch]:
    """Match each upper-floor segment to its best lower-floor counterpart."""
    matches: list[ContinuityMatch] = []
    for upper_index, upper_segment in enumerate(upper.segments):
        best = None
        for lower_index, lower_segment in enumerate(lower.segments):
            ratio, offset, angle = compare_segments(
                upper_segment, lower_segment, tolerance, angle_tolerance)
            if best is None or ratio > best[0]:
                best = (ratio, offset, angle, lower_index)
        if best is None or best[0] <= 0:
            matches.append(ContinuityMatch(upper_index, -1, "appears", 0.0,
                                           math.inf, 180.0))
        else:
            ratio, offset, angle, lower_index = best
            status = "continuous" if ratio >= full_ratio else "partial"
            matches.append(ContinuityMatch(upper_index, lower_index, status,
                                           ratio, offset, angle))
    matched_lower = {m.lower_index for m in matches if m.lower_index >= 0}
    for lower_index in range(len(lower.segments)):
        if lower_index not in matched_lower:
            matches.append(ContinuityMatch(-1, lower_index, "disappears",
                                           0.0, math.inf, 180.0))
    return matches


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
        if selected is not None and layer.casefold() not in selected:
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


def align_by_centroid(drawings: list[FloorDrawing]) -> None:
    """Translate drawings to a shared centroid; does not rotate or scale them."""
    if not drawings:
        return
    centroids = []
    for drawing in drawings:
        points = [(s.x1, s.y1) for s in drawing.segments] + [
            (s.x2, s.y2) for s in drawing.segments]
        if not points:
            centroids.append((0.0, 0.0))
        else:
            centroids.append((sum(p[0] for p in points) / len(points),
                              sum(p[1] for p in points) / len(points)))
    target = centroids[0]
    for drawing, center in zip(drawings, centroids):
        dx, dy = target[0] - center[0], target[1] - center[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            continue
        drawing.segments = [Segment(s.layer, s.x1 + dx, s.y1 + dy,
                                    s.x2 + dx, s.y2 + dy, s.entity_type)
                            for s in drawing.segments]
