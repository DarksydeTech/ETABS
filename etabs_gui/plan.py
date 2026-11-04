"""Motor geométrico de la planta (grillas, columnas, vigas, muros y losas).

Es una traducción directa del algoritmo VBA de ``ETABS-CIXTOP 4.0``
(módulos "GenerarTablasPlanta"): unifica grillas cartesianas e inclinadas,
calcula cruces, vigas entre cruces consecutivos y los vanos cerrados
(caras del diagrama planar) que se convierten en losas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

EXT_INCLINADA = 1.5
TOL = 1e-7
AREA_MIN_LOSA = 0.01
PREFIJO_VACIO = "VACIO"


@dataclass
class GridLine:
    id: str
    kind: str          # "X", "Y", "I1", "I2"
    x1: float
    y1: float
    x2: float
    y2: float
    orig_x1: float = 0.0
    orig_y1: float = 0.0
    orig_x2: float = 0.0
    orig_y2: float = 0.0


@dataclass
class Column:
    id: str
    grid_a: str
    grid_b: str
    x: float
    y: float
    kind: str
    section: str = ""
    angle: float = 0.0


@dataclass
class Beam:
    id: str
    grid: str
    grid_kind: str
    col_a: str
    col_b: str
    x: float
    y: float
    section: str = ""
    type_index: int = 1   # 1=X, 2=Y, 3=inclinada tipo 1, 4=inclinada tipo 2


@dataclass
class Slab:
    id: str
    vertex_ids: list[str]
    coords: list[tuple[float, float]]
    centroid: tuple[float, float]
    section: str = "VACIO"


@dataclass
class Wall:
    id: str
    col_a: str
    col_b: str
    cx: float
    cy: float
    length: float
    section: str = ""


@dataclass
class Plan:
    columns: list[Column] = field(default_factory=list)
    beams_x: list[Beam] = field(default_factory=list)
    beams_y: list[Beam] = field(default_factory=list)
    beams_i1: list[Beam] = field(default_factory=list)
    beams_i2: list[Beam] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)
    slabs: list[Slab] = field(default_factory=list)
    grids: list[GridLine] = field(default_factory=list)
    intersections: list[dict] = field(default_factory=list)
    extent: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @property
    def beams(self) -> list[Beam]:
        return self.beams_x + self.beams_y + self.beams_i1 + self.beams_i2

    def column_map(self) -> dict[str, Column]:
        return {c.id: c for c in self.columns}

    def summary(self) -> str:
        return (f"{len(self.columns)} columnas · {len(self.beams)} vigas · "
                f"{len(self.slabs)} losas · {len(self.walls)} muros")


def extend_segment(x1: float, y1: float, x2: float, y2: float,
                   ext: float) -> tuple[float, float, float, float]:
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9 or ext <= 0:
        return x1, y1, x2, y2
    return (x1 - dx / length * ext, y1 - dy / length * ext,
            x2 + dx / length * ext, y2 + dy / length * ext)


def segment_intersection(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    rx, ry = ax2 - ax1, ay2 - ay1
    sx, sy = bx2 - bx1, by2 - by1
    den = rx * sy - ry * sx
    if abs(den) < TOL:
        return None
    t = ((bx1 - ax1) * sy - (by1 - ay1) * sx) / den
    u = ((bx1 - ax1) * ry - (by1 - ay1) * rx) / den
    if t < -TOL or t > 1 + TOL or u < -TOL or u > 1 + TOL:
        return None
    return ax1 + t * rx, ay1 + t * ry


def build_grids(grid_x: list[tuple[str, float]], grid_y: list[tuple[str, float]],
                inclined_x: list[dict], inclined_y: list[dict]) -> list[GridLine]:
    if not grid_x and not grid_y:
        return []
    xmin = min(v for _, v in grid_x) if grid_x else 0.0
    xmax = max(v for _, v in grid_x) if grid_x else 0.0
    ymin = min(v for _, v in grid_y) if grid_y else 0.0
    ymax = max(v for _, v in grid_y) if grid_y else 0.0
    xmin_ext, xmax_ext, ymin_ext, ymax_ext = xmin, xmax, ymin, ymax
    prepared_x, prepared_y = [], []
    for item in inclined_x:
        nx1, ny1, nx2, ny2 = extend_segment(
            float(item.get("start", 0)), ymin, float(item.get("end", 0)), ymax, EXT_INCLINADA)
        prepared_x.append((item, nx1, ny1, nx2, ny2))
        xmin_ext, xmax_ext = min(xmin_ext, nx1, nx2), max(xmax_ext, nx1, nx2)
        ymin_ext, ymax_ext = min(ymin_ext, ny1, ny2), max(ymax_ext, ny1, ny2)
    for item in inclined_y:
        nx1, ny1, nx2, ny2 = extend_segment(
            xmin, float(item.get("start", 0)), xmax, float(item.get("end", 0)), EXT_INCLINADA)
        prepared_y.append((item, nx1, ny1, nx2, ny2))
        xmin_ext, xmax_ext = min(xmin_ext, nx1, nx2), max(xmax_ext, nx1, nx2)
        ymin_ext, ymax_ext = min(ymin_ext, ny1, ny2), max(ymax_ext, ny1, ny2)
    lines: list[GridLine] = []
    for gid, coord in grid_x:
        lines.append(GridLine(gid, "X", coord, ymin_ext, coord, ymax_ext,
                              coord, ymin, coord, ymax))
    for gid, coord in grid_y:
        lines.append(GridLine(gid, "Y", xmin_ext, coord, xmax_ext, coord,
                              xmin, coord, xmax, coord))
    for item, nx1, ny1, nx2, ny2 in prepared_x:
        lines.append(GridLine(str(item.get("id", "I")), "I1", nx1, ny1, nx2, ny2,
                              float(item.get("start", 0)), ymin,
                              float(item.get("end", 0)), ymax))
    for item, nx1, ny1, nx2, ny2 in prepared_y:
        lines.append(GridLine(str(item.get("id", "I")), "I2", nx1, ny1, nx2, ny2,
                              xmin, float(item.get("start", 0)),
                              xmax, float(item.get("end", 0))))
    return lines


def count_intersections(lines: list[GridLine]) -> list[dict]:
    found = []
    for i, a in enumerate(lines):
        if a.kind not in ("I1", "I2"):
            continue
        for b in lines:
            if b is a:
                continue
            if b.kind not in ("X", "Y", "I1", "I2"):
                continue
            point = segment_intersection(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1, b.x2, b.y2)
            if point:
                found.append({"grid": a.id, "crosses": b.id,
                              "x": point[0], "y": point[1]})
    return found


def _grid_parameter(line: GridLine, x: float, y: float) -> float:
    dx, dy = line.x2 - line.x1, line.y2 - line.y1
    if abs(dx) >= abs(dy):
        return (x - line.x1) / dx if abs(dx) > 1e-9 else 0.0
    return (y - line.y1) / dy if abs(dy) > 1e-9 else 0.0


def _columns_on(lines: list[GridLine]) -> list[Column]:
    columns: list[Column] = []
    for a_index, a in enumerate(lines[:-1]):
        for b in lines[a_index + 1:]:
            if a.kind == b.kind:
                continue
            point = segment_intersection(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1, b.x2, b.y2)
            if not point:
                continue
            ga, gb = (a, b) if a.kind <= b.kind else (b, a)
            columns.append(Column(
                id=f"{ga.id}-{gb.id}", grid_a=ga.id, grid_b=gb.id,
                x=point[0], y=point[1], kind=f"{ga.kind}n{gb.kind}"))
    return columns


def _beams_for(lines: list[GridLine], columns: list[Column]) -> list[dict]:
    result = []
    for index, line in enumerate(lines):
        on_line = [c for c in columns if c.grid_a == line.id or c.grid_b == line.id]
        on_line.sort(key=lambda c: _grid_parameter(line, c.x, c.y))
        for left, right in zip(on_line, on_line[1:]):
            result.append({"line": line, "a": left, "b": right})
    return result


class _FaceWalker:
    def __init__(self):
        self.vertices: list[tuple[float, float, str]] = []
        self.lookup: dict[tuple[float, float], int] = {}
        self.edges: dict[tuple[int, int], int] = {}

    def vertex(self, x: float, y: float, label: str = "") -> int:
        key = (round(x, 4) + 0.0, round(y, 4) + 0.0)
        if key in self.lookup:
            return self.lookup[key]
        index = len(self.vertices)
        self.vertices.append((x, y, label))
        self.lookup[key] = index
        return index

    def edge(self, a: int, b: int, grid_index: int) -> None:
        if a != b:
            self.edges.setdefault((a, b), grid_index)

    def next_left(self, current: int, arrival: int) -> int | None:
        ax, ay, _ = self.vertices[current]
        bx, by, _ = self.vertices[arrival]
        back = math.atan2(ay - by, ax - bx)
        best, best_angle = None, -1.0
        for (start, end), _grid in self.edges.items():
            if start != arrival or end == current:
                continue
            cx, cy, _ = self.vertices[end]
            angle = math.atan2(cy - by, cx - bx) - back
            angle %= 2 * math.pi
            if angle > best_angle:
                best_angle, best = angle, end
        return best

    def faces(self) -> list[list[int]]:
        used: set[tuple[int, int]] = set()
        faces = []
        for (start, end), _grid in list(self.edges.items()):
            if (start, end) in used:
                continue
            first = (start, end)
            current, following = start, end
            face: list[int] = []
            for _ in range(5000):
                edge = (current, following)
                if edge in used:
                    break
                used.add(edge)
                face.append(current)
                nxt = self.next_left(current, following)
                if nxt is None:
                    break
                current, following = following, nxt
                if (current, following) == first:
                    break
            if len(face) >= 3:
                faces.append(face)
        return faces


def _polygon_area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    area = _polygon_area(points)
    if abs(area) < 1e-6:
        return (sum(p[0] for p in points) / len(points),
                sum(p[1] for p in points) / len(points))
    sx = sy = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        cross = x1 * y2 - x2 * y1
        sx += (x1 + x2) * cross
        sy += (y1 + y2) * cross
    return sx / (6 * area), sy / (6 * area)


def build_plan(grid_x, grid_y, inclined_x, inclined_y, column_sections=None,
               beam_sections=None, wall_defs=None, slab_sections=None,
               default_column="", default_beam="", default_wall="",
               default_slab="") -> Plan:
    """Construye la planta completa a partir de las grillas y asignaciones."""
    lines = build_grids(grid_x, grid_y, inclined_x, inclined_y)
    if not lines:
        return Plan()
    columns = _columns_on(lines)
    column_sections = column_sections or {}
    beam_sections = beam_sections or {}
    slab_sections = slab_sections or {}
    for column in columns:
        column.section = column_sections.get(column.id, default_column)

    plan = Plan(grids=lines, columns=columns,
                intersections=count_intersections(lines))
    xmin = min(l.orig_x1 for l in lines)
    xmax = max(l.orig_x2 for l in lines)
    ymin = min(l.orig_y1 for l in lines)
    ymax = max(l.orig_y2 for l in lines)
    for line in lines:
        xmin, xmax = min(xmin, line.x1, line.x2), max(xmax, line.x1, line.x2)
        ymin, ymax = min(ymin, line.y1, line.y2), max(ymax, line.y1, line.y2)
    plan.extent = (xmin, ymin, xmax, ymax)

    prefixes = {"X": ("vx", 1), "Y": ("vy", 2), "I1": ("vi1", 3), "I2": ("vi2", 4)}
    counters = {"vx": 0, "vy": 0, "vi1": 0, "vi2": 0}
    for item in _beams_for(lines, columns):
        line: GridLine = item["line"]
        prefix, index = prefixes[line.kind]
        counters[prefix] += 1
        beam = Beam(
            id=f"{prefix.upper()}-{counters[prefix]:03d}", grid=line.id,
            grid_kind=line.kind, col_a=item["a"].id, col_b=item["b"].id,
            x=(item["a"].x + item["b"].x) / 2.0,
            y=(item["a"].y + item["b"].y) / 2.0,
            section=default_beam, type_index=index)
        beam.section = beam_sections.get(beam.id, default_beam)
        {1: plan.beams_x, 2: plan.beams_y,
         3: plan.beams_i1, 4: plan.beams_i2}[index].append(beam)

    walker = _FaceWalker()
    for grid_index, line in enumerate(lines):
        on_line = [c for c in columns if c.grid_a == line.id or c.grid_b == line.id]
        entries = [(line.x1, line.y1, ""), (line.x2, line.y2, "")]
        entries += [(c.x, c.y, c.id) for c in on_line]
        entries.sort(key=lambda item: _grid_parameter(line, item[0], item[1]))
        unique = []
        for item in entries:
            if not unique or (round(item[0], 4) != round(unique[-1][0], 4)
                              or round(item[1], 4) != round(unique[-1][1], 4)):
                unique.append(item)
        indices = [walker.vertex(x, y, label) for x, y, label in unique]
        for left, right in zip(indices, indices[1:]):
            if left != right:
                walker.edge(left, right, grid_index)
                walker.edge(right, left, grid_index)

    slab_names = list(slab_sections.keys())
    for face in walker.faces():
        points = [(walker.vertices[i][0], walker.vertices[i][1]) for i in face]
        area = _polygon_area(points)
        if area <= AREA_MIN_LOSA:
            continue
        labels = [walker.vertices[i][2] for i in face]
        number = len(plan.slabs) + 1
        default_id = slab_names[number - 1] if number <= len(slab_names) else f"L-{number:03d}"
        slab = Slab(id=default_id, vertex_ids=labels, coords=points,
                    centroid=_polygon_centroid(points),
                    section=default_slab)
        slab.section = slab_sections.get(slab.id, default_slab)
        plan.slabs.append(slab)

    lookup = plan.column_map()
    for index, definition in enumerate(wall_defs or [], start=1):
        a_id = str(definition.get("a", "")).strip()
        b_id = str(definition.get("b", "")).strip()
        wall_id = str(definition.get("id", "")).strip() or f"M-{index:03d}"
        if a_id in lookup and b_id in lookup:
            ca, cb = lookup[a_id], lookup[b_id]
            wall = Wall(id=wall_id, col_a=a_id, col_b=b_id,
                        cx=(ca.x + cb.x) / 2.0, cy=(ca.y + cb.y) / 2.0,
                        length=math.hypot(cb.x - ca.x, cb.y - ca.y),
                        section=str(definition.get("section", "") or default_wall))
        else:
            wall = Wall(id=wall_id, col_a=a_id, col_b=b_id, cx=0.0, cy=0.0,
                        length=0.0,
                        section=str(definition.get("section", "") or default_wall))
        plan.walls.append(wall)
    return plan


def grid_ids_and_coords(grids) -> tuple[list[str], list[float]]:
    return [g.id for g in grids], [g.coord for g in grids]


def as_tuples(grids) -> list[tuple[str, float]]:
    return [(g.id, g.coord) for g in grids]
