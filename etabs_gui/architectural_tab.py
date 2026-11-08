"""Interfaz Tkinter para importar y comparar plantas arquitectónicas DXF."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .architectural import (FloorDrawing, alignment_offsets_by_bounds,
                            apply_alignment_offsets, compare_floors, read_dxf)


class ArchitecturalTab(ttk.Frame):
    COLORS = {"continuous": "#23934b", "partial": "#d49b16",
              "appears": "#2878c8", "disappears": "#c83b35"}

    def __init__(self, master):
        super().__init__(master, padding=8)
        self.drawings: list[FloorDrawing] = []
        self.matches = []
        self.comparisons = []
        self._build()

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Importar DXF de nivel…",
                   command=self.import_dxf).pack(side="left")
        ttk.Button(toolbar, text="Alinear por centro de extensión",
                   command=self.align).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Comparar niveles",
                   command=self.compare).pack(side="left")
        self.summary = tk.StringVar(value="Importa un archivo DXF por cada nivel para comenzar.")
        ttk.Label(self, textvariable=self.summary).pack(anchor="w", pady=(0, 6))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, width=245)
        right = ttk.Frame(body)
        body.add(left, weight=0)
        body.add(right, weight=1)
        ttk.Label(left, text="Niveles importados", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.levels = ttk.Treeview(left, columns=("segments", "source"),
                                   show="tree headings", height=12)
        self.levels.heading("#0", text="Nivel")
        self.levels.heading("segments", text="Segmentos")
        self.levels.heading("source", text="Archivo")
        self.levels.column("#0", width=95)
        self.levels.column("segments", width=70, anchor="e")
        self.levels.column("source", width=130)
        self.levels.pack(fill="both", expand=True, pady=5)
        ttk.Button(left, text="Eliminar nivel seleccionado",
                   command=self.remove_level).pack(fill="x")

        controls = ttk.Frame(right)
        controls.pack(fill="x", pady=(0, 5))
        ttk.Label(controls, text="Vista:").pack(side="left")
        self.view_mode = tk.StringVar(value="Comparación")
        ttk.Combobox(controls, textvariable=self.view_mode, state="readonly",
                     values=("Comparación", "Nivel inferior", "Nivel superior"),
                     width=18).pack(side="left", padx=5)
        ttk.Label(controls, text="  Par:").pack(side="left")
        self.pair_var = tk.StringVar()
        self.pair_selector = ttk.Combobox(controls, textvariable=self.pair_var,
                                           state="readonly", width=24)
        self.pair_selector.pack(side="left", padx=5)
        self.pair_selector.bind("<<ComboboxSelected>>", self.select_pair)
        self.canvas = tk.Canvas(right, bg="#ffffff", highlightthickness=1,
                                highlightbackground="#cbd5e1")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())

        legend = ttk.Frame(right)
        legend.pack(fill="x", pady=(5, 0))
        for key, label in (("continuous", "Continuidad"), ("partial", "Parcial"),
                           ("appears", "Aparece"), ("disappears", "Desaparece")):
            chip = tk.Label(legend, text=f"  {label}  ", fg=self.COLORS[key],
                            relief="groove", padx=3, pady=2)
            chip.pack(side="left", padx=(0, 5))

    def import_dxf(self):
        path = filedialog.askopenfilename(
            title="Seleccionar plano DXF",
            filetypes=[("Drawing Exchange Format", "*.dxf"), ("Todos", "*.*")])
        if not path:
            return
        name = simpledialog.askstring("Nombre del nivel", "Ej. Piso 1, Piso 2:")
        if name is None:
            return
        try:
            drawing = read_dxf(path, name)
        except Exception as exc:
            messagebox.showerror("Importar DXF", str(exc), parent=self)
            return
        if not drawing.segments:
            messagebox.showwarning("DXF sin geometría lineal",
                                   "No se encontraron líneas, polilíneas, arcos o círculos.", parent=self)
            return
        if any(d.name.casefold() == drawing.name.casefold() for d in self.drawings):
            messagebox.showerror("Nivel repetido", "Ya existe un nivel con ese nombre.", parent=self)
            return
        self.drawings.append(drawing)
        self._refresh_levels()
        self.summary.set(f"{len(self.drawings)} nivel(es) · {len(drawing.segments)} segmentos en {drawing.name}")
        self.redraw()

    def remove_level(self):
        selected = self.levels.selection()
        if not selected:
            return
        index = int(selected[0])
        self.drawings.pop(index)
        self.matches = []
        self._refresh_levels()
        self.redraw()

    def align(self):
        if len(self.drawings) < 2:
            messagebox.showinfo("Alinear", "Importa al menos dos niveles.", parent=self)
            return
        offsets = alignment_offsets_by_bounds(self.drawings)
        lines = ["Desplazamientos propuestos respecto al primer nivel (unidades DXF):", ""]
        for drawing, (dx, dy) in zip(self.drawings, offsets):
            lines.append(f"{drawing.name}: ΔX = {dx:.4f} · ΔY = {dy:.4f}")
        if all(abs(dx) < 1e-9 and abs(dy) < 1e-9 for dx, dy in offsets):
            messagebox.showinfo("Alineación", "Los centros de las extensiones geométricas ya coinciden. No se modificó ningún plano.", parent=self)
            self.summary.set("Sin desplazamientos: los centros de extensión coinciden.")
            return
        if not messagebox.askyesno("Confirmar alineación", "\n".join(lines) +
                                   "\n\n¿Aplicar estos desplazamientos? Esta operación modifica las coordenadas en memoria.", parent=self):
            return
        apply_alignment_offsets(self.drawings, offsets)
        self.matches = []
        self.summary.set("Alineación aplicada por centro de extensión. Vuelve a comparar los niveles.")
        self.redraw()

    def compare(self):
        if len(self.drawings) < 2:
            messagebox.showinfo("Comparar", "Importa al menos dos niveles.", parent=self)
            return
        # Compare every consecutive pair, not only the last two imported floors.
        self.comparisons = [
            (i, i + 1, compare_floors(self.drawings[i], self.drawings[i + 1]))
            for i in range(len(self.drawings) - 1)
        ]
        labels = [f"{self.drawings[lo].name} → {self.drawings[hi].name}"
                  for lo, hi, _matches in self.comparisons]
        self.pair_selector["values"] = labels
        self.pair_selector.current(len(labels) - 1)
        self.select_pair()

    def select_pair(self, _event=None):
        selected = self.pair_selector.current()
        if selected < 0 or selected >= len(self.comparisons):
            return
        lower_index, upper_index, self.matches = self.comparisons[selected]
        counts = {key: sum(m.status == key for m in self.matches)
                  for key in ("continuous", "partial", "appears", "disappears")}
        self.summary.set(
            f"{self.drawings[lower_index].name} → {self.drawings[upper_index].name}: "
            f"{counts['continuous']} continuos · {counts['partial']} parciales · "
            f"{counts['appears']} aparecen · {counts['disappears']} desaparecen "
            f"({len(self.comparisons)} pares analizados)")
        self.redraw()

    def _refresh_levels(self):
        self.levels.delete(*self.levels.get_children())
        for index, drawing in enumerate(self.drawings):
            self.levels.insert("", "end", iid=str(index),
                               text=drawing.name,
                               values=(len(drawing.segments), drawing.source.split("/")[-1].split("\\")[-1]))

    def redraw(self):
        if not hasattr(self, "canvas"):
            return
        canvas = self.canvas
        canvas.delete("all")
        if not self.drawings:
            canvas.create_text(20, 20, anchor="nw",
                               text="Importa los planos DXF de los niveles que deseas comparar.",
                               fill="#64748b")
            return
        selected = self.view_mode.get()
        if len(self.drawings) == 1 or selected == "Nivel inferior":
            drawing = self.drawings[-2] if len(self.drawings) > 1 and selected == "Nivel inferior" else self.drawings[-1]
            segments = [(s, "#64748b", 1) for s in drawing.segments]
        elif selected == "Nivel superior":
            drawing = self.drawings[-1]
            segments = [(s, "#2878c8", 1) for s in drawing.segments]
        elif self.matches and len(self.drawings) >= 2:
            selected_pair = self.pair_selector.current()
            if selected_pair < 0 or selected_pair >= len(self.comparisons):
                lower_index, upper_index = len(self.drawings) - 2, len(self.drawings) - 1
            else:
                lower_index, upper_index, _ = self.comparisons[selected_pair]
            lower, upper = self.drawings[lower_index], self.drawings[upper_index]
            segments = []
            for match in self.matches:
                if match.lower_index >= 0:
                    s = lower.segments[match.lower_index]
                    segments.append((s, self.COLORS[match.status], 3 if match.status == "continuous" else 2))
                if match.upper_index >= 0:
                    s = upper.segments[match.upper_index]
                    segments.append((s, self.COLORS[match.status], 3 if match.status == "continuous" else 2))
        else:
            segments = [(s, "#94a3b8", 1) for d in self.drawings[-2:] for s in d.segments]

        if not segments:
            return
        xs = [v for s, _, _ in segments for v in (s.x1, s.x2)]
        ys = [v for s, _, _ in segments for v in (s.y1, s.y2)]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        width, height = max(canvas.winfo_width() - 40, 100), max(canvas.winfo_height() - 40, 100)
        scale = min(width / max(xmax - xmin, 1e-6), height / max(ymax - ymin, 1e-6))
        ox = (canvas.winfo_width() - (xmax - xmin) * scale) / 2
        oy = (canvas.winfo_height() - (ymax - ymin) * scale) / 2

        def screen(x, y):
            return ox + (x - xmin) * scale, canvas.winfo_height() - oy - (y - ymin) * scale

        for segment, color, line_width in segments:
            x1, y1 = screen(segment.x1, segment.y1)
            x2, y2 = screen(segment.x2, segment.y2)
            canvas.create_line(x1, y1, x2, y2, fill=color, width=line_width)

        canvas.create_text(12, 10, anchor="nw",
                           text=f"{len(segments)} trazos mostrados · unidades DXF sin convertir",
                           fill="#475569", font=("Segoe UI", 8))
