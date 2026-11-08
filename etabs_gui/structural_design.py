"""Generación preliminar de alternativas estructurales desde geometría DXF.

Los resultados son candidatos editables para predimensionamiento, no diseño
estructural ni comprobación normativa. Unidades geométricas normalizadas a m.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable

from .architectural import FloorDrawing, Segment


@dataclass(frozen=True)
class StructuralNode:
    id: str
    x: float
    y: float
    score: float
    reasons: tuple[str, ...]
    layers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BeamCandidate:
    id: str
    start: str
    end: str
    length: float
    direction: str
    width_cm: int
    depth_cm: int


@dataclass(frozen=True)
class SlabPanel:
    id: str
    width: float
    length: float
    area: float
    aspect_ratio: float
    behavior: str
    span_direction: str


@dataclass
class StructuralProposal:
    system: str
    nodes: list[StructuralNode] = field(default_factory=list)
    beams: list[BeamCandidate] = field(default_factory=list)
    slabs: list[SlabPanel] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


SYSTEMS = (
    "Pórticos de concreto armado",
    "Sistema dual de concreto armado",
    "Albañilería confinada",
    "Sistema mixto (requiere definición)",
)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _intersection(a: Segment, b: Segment, tol: float = 1e-8):
    x1, y1, x2, y2 = a.x1, a.y1, a.x2, a.y2
    x3, y3, x4, y4 = b.x1, b.y1, b.x2, b.y2
    den = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if abs(den) <= tol:
        return None
    det1, det2 = x1*y2-y1*x2, x3*y4-y3*x4
    x = (det1*(x3-x4) - (x1-x2)*det2) / den
    y = (det1*(y3-y4) - (y1-y2)*det2) / den
    if (min(x1,x2)-tol <= x <= max(x1,x2)+tol and
            min(y1,y2)-tol <= y <= max(y1,y2)+tol and
            min(x3,x4)-tol <= x <= max(x3,x4)+tol and
            min(y3,y4)-tol <= y <= max(y3,y4)+tol):
        return x, y
    return None


def _cluster_points(points, tolerance: float):
    clusters: list[list] = []
    for x, y, reason, layer in points:
        for cluster in clusters:
            if _distance((x, y), (cluster[0][0], cluster[0][1])) <= tolerance:
                cluster.append((x, y, reason, layer))
                break
        else:
            clusters.append([(x, y, reason, layer)])
    return clusters


def _round_section(value: float, minimum: int = 25) -> int:
    return max(minimum, int(math.ceil(value / 5.0) * 5))


def generate_proposal(
    drawing: FloorDrawing,
    layer_categories: dict[str, str] | None = None,
    *,
    system: str = SYSTEMS[0],
    unit_scale: float = 1.0,
    tolerance: float = 0.15,
    stories: int = 1,
    fc: float = 210.0,
    dead_load: float = 6.0,
    live_load: float = 2.0,
    max_span: float = 7.0,
) -> StructuralProposal:
    """Build a transparent first-pass proposal from classified DXF geometry.

    unit_scale converts drawing units to metres (m=1, cm=.01, mm=.001).
    """
    if system not in SYSTEMS:
        raise ValueError("Sistema estructural no reconocido.")
    if unit_scale <= 0 or tolerance <= 0 or fc <= 0 or stories < 1:
        raise ValueError("Unidades, tolerancia, fc y número de pisos deben ser positivos.")
    categories = layer_categories or {}

    def category(segment):
        return categories.get(segment.layer, _default_category(segment.layer))

    walls = [s for s in drawing.segments if category(s) in {"wall", "low_wall"}]
    explicit_columns = [s for s in drawing.segments if category(s) == "column"]
    structural_lines = walls + explicit_columns
    points = []
    for segment in structural_lines:
        x1, y1 = segment.x1 * unit_scale, segment.y1 * unit_scale
        x2, y2 = segment.x2 * unit_scale, segment.y2 * unit_scale
        source = "Extremo de elemento"
        points.extend([(x1, y1, source, segment.layer),
                       (x2, y2, source, segment.layer)])
    for i, first in enumerate(structural_lines):
        for second in structural_lines[i+1:]:
            point = _intersection(first, second)
            if point:
                points.append((point[0]*unit_scale, point[1]*unit_scale,
                               "Intersección de elementos", first.layer))
                points.append((point[0]*unit_scale, point[1]*unit_scale,
                               "Intersección de elementos", second.layer))

    clusters = _cluster_points(points, tolerance)
    nodes = []
    for index, cluster in enumerate(clusters, start=1):
        x = sum(p[0] for p in cluster) / len(cluster)
        y = sum(p[1] for p in cluster) / len(cluster)
        reasons = tuple(sorted({p[2] for p in cluster}))
        layers = tuple(sorted({p[3] for p in cluster}))
        score = min(100.0, 45.0 + 20.0 * ("Intersección de elementos" in reasons)
                    + min(20.0, len(layers)*5.0) + min(15.0, len(cluster)*2.0))
        nodes.append(StructuralNode(f"CAND-{index:03d}", x, y, score, reasons, layers))

    nodes.sort(key=lambda n: (n.x, n.y))
    # Keep all geometric candidates; do not silently declare them as final columns.
    beams = []
    for direction in ("X", "Y"):
        ordered = sorted(nodes, key=(lambda n: (n.y, n.x)) if direction == "X"
                         else (lambda n: (n.x, n.y)))
        for i, first in enumerate(ordered):
            for second in ordered[i+1:]:
                dx, dy = second.x-first.x, second.y-first.y
                aligned = abs(dy) <= tolerance if direction == "X" else abs(dx) <= tolerance
                length = math.hypot(dx, dy)
                if not aligned:
                    if (direction == "X" and dy > tolerance) or (direction == "Y" and dx > tolerance):
                        break
                    continue
                if length < 1.5 or length > max_span:
                    continue
                middle = [n for n in nodes if n.id not in (first.id, second.id)
                          and (min(first.x, second.x)-tolerance <= n.x <= max(first.x, second.x)+tolerance)
                          and (min(first.y, second.y)-tolerance <= n.y <= max(first.y, second.y)+tolerance)]
                if middle:
                    continue
                depth = _round_section(length * 100 / 10)
                width = _round_section(max(25.0, depth * 0.4))
                beams.append(BeamCandidate(f"V-{direction}-{len(beams)+1:03d}",
                                           first.id, second.id, length, direction, width, depth))

    slabs = []
    xs = sorted({round(n.x, 3) for n in nodes})
    ys = sorted({round(n.y, 3) for n in nodes})
    node_lookup = {(round(n.x, 3), round(n.y, 3)): n for n in nodes}
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            if (x1-x0) <= tolerance or (y1-y0) <= tolerance:
                continue
            corners = [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
            if all(any(_distance(c, (n.x,n.y)) <= tolerance for n in nodes) for c in corners):
                short, long = sorted((x1-x0, y1-y0))
                ratio = long / short
                slabs.append(SlabPanel(f"L-{len(slabs)+1:03d}", short, long,
                                       short*long, ratio,
                                       "Unidireccional (candidato)" if ratio >= 2.0
                                       else "Bidireccional (candidato)",
                                       "Dirección de luz corta" if ratio >= 2.0
                                       else "Revisar apoyos y continuidad"))

    if not structural_lines:
        notes = ["No se identificaron capas clasificadas como muro o columna.",
                 "Clasifica las capas DXF antes de generar candidatos; no se inferirá estructura desde líneas desconocidas."]
    else:
        notes = ["Los puntos son candidatos geométricos; verifica que cada uno sea compatible con arquitectura y cimentación.",
                 "La detección de paños solo reconoce celdas rectangulares aproximadas entre candidatos.",
                 "Las vigas propuestas son conexiones geométricas preliminares, no elementos comprobados."]
    if system == "Albañilería confinada":
        notes.append("En albañilería confinada, los candidatos representan posibles elementos de confinamiento; los muros portantes deben verificarse como paños estructurales según E.070.")
    elif system == "Sistema dual de concreto armado":
        notes.append("La propuesta no dimensiona placas: su ubicación, longitud y participación deben definirse y verificarse con el análisis sísmico E.030.")
    elif system == "Sistema mixto (requiere definición)":
        notes.append("Define qué elementos resisten cargas gravitacionales y laterales antes de considerar válida la idealización mixta.")
    else:
        notes.append("Para pórticos, verifica rigidez lateral en ambas direcciones, derivas, torsión y jerarquía resistente.")

    # Approximate tributary area and axial sizing: explicit assumptions, not code design.
    tributary_area = (max_span/2)**2
    service_load = max(0.0, dead_load + live_load) * tributary_area * max(stories, 1)
    axial_kgf = service_load * 101.9716
    area_cm2 = axial_kgf / max(0.35 * fc, 1.0)
    column_side = _round_section(math.sqrt(max(area_cm2, 0.0)))
    notes.append(f"Referencia de sección cuadrada preliminar: {column_side}×{column_side} cm, basada en área tributaria supuesta {tributary_area:.2f} m² y carga de servicio {dead_load+live_load:.2f} kN/m²; no sustituye el análisis de cargas ni la verificación de interacción.")
    if not nodes:
        notes.append("No se generaron candidatos. Revisa las capas asignadas y la escala del DXF.")

    return StructuralProposal(system, nodes, beams, slabs, notes, {
        "candidate_columns": len(nodes), "candidate_beams": len(beams),
        "candidate_slabs": len(slabs), "stories": stories, "fc": fc,
        "reference_column_cm": column_side,
        "unit_scale_to_m": unit_scale,
        "dead_load_kN_m2": dead_load, "live_load_kN_m2": live_load,
    })


def _default_category(layer: str) -> str:
    # Import lazily to avoid duplicating the classification table.
    from .architectural import default_layer_category
    return default_layer_category(layer)


def evaluate_alternatives(proposal: StructuralProposal) -> list[dict]:
    """Rank three transparent candidate subsets; user approval is always required."""
    candidates = proposal.nodes
    if not candidates:
        return []
    variants = (
        ("Mayor regularidad", 1.0, "Conserva todos los candidatos para revisión de rigidez y continuidad."),
        ("Equilibrada", 0.8, "Prioriza candidatos con mayor puntuación geométrica."),
        ("Menor intervención", 0.6, "Reduce candidatos; exige revisar luces y derivas con especial cuidado."),
    )
    results = []
    for name, fraction, description in variants:
        count = max(1, math.ceil(len(candidates)*fraction))
        selected = sorted(candidates, key=lambda n: (-n.score, n.x, n.y))[:count]
        results.append({
            "name": name, "description": description,
            "selected_nodes": [n.id for n in selected],
            "candidate_count": count,
            "mean_score": round(sum(n.score for n in selected)/count, 1),
            "beam_count": sum(1 for b in proposal.beams
                             if b.start in {n.id for n in selected}
                             and b.end in {n.id for n in selected}),
        })
    return results
