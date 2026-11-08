"""Interfaz de propuesta estructural preliminar conectada al analizador DXF."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .structural_design import SYSTEMS, evaluate_alternatives, generate_proposal


class StructuralDesignTab(ttk.Frame):
    """Workspace vectorial ampliado para revisar la propuesta sobre el DXF."""

    def __init__(self, master, architectural_tab, project):
        super().__init__(master, padding=8)
        self.architectural_tab = architectural_tab
        self.project = project
        self.proposal = None
        self.alternatives = []
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._fit_transform = None
        self._drag_origin = None
        self._selected_ids = set()
        self._display_unit_scale = 1.0
        self._build()

    def _build(self):
        ttk.Label(self, text="Propuesta estructural automática",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(
            self,
            text="El DXF se utiliza como base de análisis. La propuesta se presenta en un visor vectorial independiente para revisar su relación con la arquitectura.",
            wraplength=1300
        ).pack(anchor="w", pady=(2, 7))

        controls = ttk.LabelFrame(self, text="Parámetros de interpretación y predimensionamiento", padding=7)
        controls.pack(fill="x", pady=(0, 7))
        self.system = tk.StringVar(value=SYSTEMS[0])
        self.units = tk.StringVar(value="m")
        self.fc = tk.StringVar(value="210")
        self.dead = tk.StringVar(value="6")
        self.live = tk.StringVar(value="2")
        self.tolerance = tk.StringVar(value="0.15")
        self.max_span = tk.StringVar(value="7")
        self.floor = tk.StringVar(value=str(max(1, len(self.project.stories))))
        fields = [
            ("Sistema", self.system, SYSTEMS, 34),
            ("Unidad DXF", self.units, ("m", "cm", "mm"), 6),
            ("fc (kg/cm²)", self.fc, None, 8),
            ("Carga muerta (kN/m²)", self.dead, None, 8),
            ("Carga viva (kN/m²)", self.live, None, 8),
            ("Tolerancia (m)", self.tolerance, None, 8),
            ("Luz máxima (m)", self.max_span, None, 8),
            ("Pisos", self.floor, None, 6),
        ]
        for index, (label, variable, options, width) in enumerate(fields):
            row, col = divmod(index, 4)
            cell = ttk.Frame(controls)
            cell.grid(row=row, column=col, sticky="w", padx=5, pady=3)
            ttk.Label(cell, text=label).pack(anchor="w")
            if options:
                ttk.Combobox(cell, textvariable=variable, values=options,
                             state="readonly", width=width).pack(anchor="w")
            else:
                ttk.Entry(cell, textvariable=variable, width=width).pack(anchor="w")

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 7))
        ttk.Button(actions, text="Generar propuesta y evaluar alternativas",
                   command=self.generate).pack(side="left")
        self.level_var = tk.StringVar()
        ttk.Label(actions, text="Nivel DXF:").pack(side="left", padx=(10, 3))
        self.level_selector = ttk.Combobox(actions, textvariable=self.level_var,
                                           state="readonly", width=17)
        self.level_selector.pack(side="left")
        self.alt_var = tk.StringVar()
        ttk.Label(actions, text="Alternativa:").pack(side="left", padx=(10, 3))
        self.alt_selector = ttk.Combobox(actions, textvariable=self.alt_var,
                                         state="readonly", width=20)
        self.alt_selector.pack(side="left")
        self.alt_selector.bind("<<ComboboxSelected>>", self.show_alternative)
        self.summary = tk.StringVar(value="Importa y clasifica los DXF en Continuidad arquitectónica.")
        ttk.Label(actions, textvariable=self.summary).pack(side="left", padx=10)

        # El visor ocupa el área principal; las tablas y advertencias quedan a un lado.
        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)
        viewer = ttk.Frame(body)
        side = ttk.Frame(body, width=390)
        body.add(viewer, weight=5)
        body.add(side, weight=2)

        view_toolbar = ttk.Frame(viewer)
        view_toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(view_toolbar, text="Ajustar a plano", command=self.fit_view).pack(side="left")
        ttk.Button(view_toolbar, text="−", width=3, command=lambda: self.zoom_at(0.8)).pack(side="left", padx=(5, 2))
        ttk.Button(view_toolbar, text="+", width=3, command=lambda: self.zoom_at(1.25)).pack(side="left", padx=2)
        ttk.Label(view_toolbar, text="Rueda: zoom · Arrastrar con botón central/derecho: desplazar").pack(side="left", padx=9)
        self.canvas = tk.Canvas(viewer, bg="#fbfcfe", highlightthickness=1,
                                highlightbackground="#94a3b8", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self._wheel_linux(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self._wheel_linux(e, -1))
        for button in (2, 3):
            self.canvas.bind(f"<ButtonPress-{button}>", self._pan_start)
            self.canvas.bind(f"<B{button}-Motion>", self._pan_move)
        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", self._pan_move)

        legend = ttk.Frame(viewer)
        legend.pack(fill="x", pady=(4, 0))
        for color, label in (("#aab4c0", "Arquitectura DXF"),
                             ("#dc8b22", "Candidatos estructurales"),
                             ("#2474b8", "Vigas candidatas"),
                             ("#d04444", "Punto seleccionado")):
            tk.Label(legend, text=f"  {label}  ", fg=color, relief="groove",
                     padx=3, pady=2).pack(side="left", padx=(0, 5))

        notes_frame = ttk.LabelFrame(side, text="Criterios y advertencias de ingeniería", padding=5)
        notes_frame.pack(fill="x", pady=(0, 7))
        self.notes_text = tk.Text(notes_frame, height=7, wrap="word",
                                  font=("Segoe UI", 8), relief="flat")
        self.notes_text.pack(fill="x", expand=True)
        self.notes_text.insert("1.0", "Genera una propuesta para consultar los criterios y las limitaciones.")
        self.notes_text.configure(state="disabled")

        tables = ttk.Panedwindow(side, orient="vertical")
        tables.pack(fill="both", expand=True)
        left = ttk.LabelFrame(tables, text="Candidatos de columna", padding=4)
        right = ttk.LabelFrame(tables, text="Vigas y paños preliminares", padding=4)
        tables.add(left, weight=1)
        tables.add(right, weight=1)
        self.nodes = self._tree(left, ("id", "x", "y", "score"),
                                ("ID", "X (m)", "Y (m)", "Puntaje"))
        self.members = self._tree(right, ("id", "length", "section", "kind"),
                                  ("Elemento", "Luz / área", "Sección / dimensión", "Tipo"))

    @staticmethod
    def _tree(parent, keys, labels):
        tree = ttk.Treeview(parent, columns=keys, show="headings", height=8)
        for key, label in zip(keys, labels):
            tree.heading(key, text=label)
            tree.column(key, width=95, anchor="center")
        tree.pack(fill="both", expand=True)
        return tree

    def generate(self):
        drawings = self.architectural_tab.drawings
        if not drawings:
            messagebox.showinfo("Propuesta estructural",
                                "Primero importa un DXF en Continuidad arquitectónica.", parent=self)
            return
        try:
            names = [drawing.name for drawing in drawings]
            self.level_selector["values"] = names
            if self.level_var.get() not in names:
                self.level_selector.current(0)
            selected_drawing = next(d for d in drawings if d.name == self.level_var.get())
            number = int(self.floor.get())
            scale = {"m": 1.0, "cm": 0.01, "mm": 0.001}[self.units.get()]
            self._display_unit_scale = scale
            self.proposal = generate_proposal(
                selected_drawing, self.architectural_tab.layer_categories,
                system=self.system.get(), unit_scale=scale,
                tolerance=float(self.tolerance.get()), stories=max(1, number),
                fc=float(self.fc.get()), dead_load=float(self.dead.get()),
                live_load=float(self.live.get()), max_span=float(self.max_span.get()))
            self.alternatives = evaluate_alternatives(self.proposal)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Parámetros inválidos", str(exc), parent=self)
            return

        self.nodes.delete(*self.nodes.get_children())
        self.members.delete(*self.members.get_children())
        for node in self.proposal.nodes:
            self.nodes.insert("", "end", values=(node.id, f"{node.x:.2f}",
                                                  f"{node.y:.2f}", f"{node.score:.0f}"))
        for beam in self.proposal.beams:
            section = (f"{beam.width_cm}×{beam.depth_cm} cm" if beam.width_cm
                       else "Por definir según sistema")
            self.members.insert("", "end", values=(beam.id, f"{beam.length:.2f} m",
                                                    section, f"Viga {beam.direction}"))
        for slab in self.proposal.slabs:
            self.members.insert("", "end", values=(slab.id, f"{slab.area:.2f} m²",
                                                    f"{slab.width:.2f}×{slab.length:.2f} m",
                                                    slab.behavior))
        self.summary.set(f"{len(self.proposal.nodes)} candidatos · "
                         f"{len(self.proposal.beams)} vigas · {len(self.proposal.slabs)} paños")
        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", "\n".join(f"• {note}" for note in self.proposal.notes))
        self.notes_text.configure(state="disabled")
        self.alt_selector["values"] = [item["name"] for item in self.alternatives]
        if self.alternatives:
            self.alt_selector.current(0)
        self._zoom = 1.0
        self._offset_x = self._offset_y = 0.0
        self.show_alternative()
        self.fit_view()

    def show_alternative(self, _event=None):
        if not self.proposal or not self.alternatives:
            return
        item = next((entry for entry in self.alternatives
                     if entry["name"] == self.alt_var.get()), self.alternatives[0])
        self._selected_ids = set(item["selected_nodes"])
        self.summary.set(f"{item['name']}: {item['candidate_count']} candidatos · "
                         f"{item['beam_count']} vigas · puntaje medio {item['mean_score']}")
        self._redraw()

    def _current_drawing(self):
        name = self.level_var.get()
        return next((d for d in self.architectural_tab.drawings if d.name == name), None)

    def fit_view(self):
        drawing = self._current_drawing()
        points = []
        if drawing:
            points.extend((v * self._display_unit_scale, w * self._display_unit_scale)
                          for s in drawing.segments
                          for v, w in ((s.x1, s.y1), (s.x2, s.y2)))
        if self.proposal:
            points.extend((n.x, n.y) for n in self.proposal.nodes)
            points.extend((v, w) for s in self.proposal.grid_lines
                          for v, w in ((s.x1, s.y1), (s.x2, s.y2)))
        if not points:
            self._redraw()
            return
        xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
        ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
        span_x, span_y = max(xmax - xmin, 1e-6), max(ymax - ymin, 1e-6)
        cw, ch = max(self.canvas.winfo_width(), 200), max(self.canvas.winfo_height(), 200)
        scale = min((cw - 70) / span_x, (ch - 70) / span_y)
        self._fit_transform = (xmin, ymin, (xmin + xmax) / 2, (ymin + ymax) / 2, scale)
        self._zoom = 1.0
        self._offset_x = self._offset_y = 0.0
        self._redraw()

    def zoom_at(self, factor, x=None, y=None):
        if not self.proposal and not self._current_drawing():
            return
        x = self.canvas.winfo_width() / 2 if x is None else x
        y = self.canvas.winfo_height() / 2 if y is None else y
        old = self._zoom
        self._zoom = min(30.0, max(0.08, old * factor))
        ratio = self._zoom / old
        cx, cy = self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2
        self._offset_x = x - cx - (x - cx - self._offset_x) * ratio
        self._offset_y = y - cy - (y - cy - self._offset_y) * ratio
        self._redraw()

    def _on_mousewheel(self, event):
        self.zoom_at(1.15 if event.delta > 0 else 1 / 1.15, event.x, event.y)
        return "break"

    def _wheel_linux(self, event, direction):
        self.zoom_at(1.15 if direction > 0 else 1 / 1.15, event.x, event.y)
        return "break"

    def _pan_start(self, event):
        self._drag_origin = (event.x, event.y, self._offset_x, self._offset_y)

    def _pan_move(self, event):
        if self._drag_origin is None:
            return
        x, y, ox, oy = self._drag_origin
        self._offset_x = ox + event.x - x
        self._offset_y = oy + event.y - y
        self._redraw()

    def _redraw(self):
        if not hasattr(self, "canvas"):
            return
        canvas = self.canvas
        canvas.delete("all")
        drawing = self._current_drawing()
        if not drawing and not self.proposal:
            canvas.create_text(24, 24, anchor="nw",
                               text="Importa los DXF y genera una propuesta estructural.",
                               fill="#64748b", font=("Segoe UI", 11))
            return

        if self._fit_transform is None:
            self.fit_view()
            return
        xmin, ymin, center_x, center_y, base_scale = self._fit_transform
        scale = base_scale * self._zoom
        cx = canvas.winfo_width() / 2 + self._offset_x
        cy = canvas.winfo_height() / 2 + self._offset_y

        def screen(x, y):
            return cx + (x - center_x) * scale, cy - (y - center_y) * scale

        # DXF as a subdued reference layer, not as the output format of the proposal.
        if drawing:
            for segment in drawing.segments:
                x1, y1 = screen(segment.x1 * self._display_unit_scale,
                                segment.y1 * self._display_unit_scale)
                x2, y2 = screen(segment.x2 * self._display_unit_scale,
                                segment.y2 * self._display_unit_scale)
                canvas.create_line(x1, y1, x2, y2, fill="#c4cbd4", width=1)

        if self.proposal:
            # DXF grid/axis lines are displayed as a separate guide layer.
            for guide in self.proposal.grid_lines:
                gx1, gy1 = screen(guide.x1, guide.y1)
                gx2, gy2 = screen(guide.x2, guide.y2)
                canvas.create_line(gx1, gy1, gx2, gy2, fill="#2b9ca3",
                                   width=1, dash=(8, 5))
            by_id = {node.id: node for node in self.proposal.nodes}
            selected = self._selected_ids or set(by_id)
            for beam in self.proposal.beams:
                if beam.start not in selected or beam.end not in selected:
                    continue
                a, b = by_id[beam.start], by_id[beam.end]
                x1, y1 = screen(a.x, a.y)
                x2, y2 = screen(b.x, b.y)
                canvas.create_line(x1, y1, x2, y2, fill="#2474b8",
                                   width=max(2, min(6, scale * 0.045)), capstyle="round")
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                canvas.create_text(mx, my - 8, text=f"{beam.length:.2f} m",
                                   fill="#175b91", font=("Segoe UI", 8, "bold"),
                                   tags=("beam_label",))
            for node in self.proposal.nodes:
                x, y = screen(node.x, node.y)
                is_selected = node.id in selected
                radius = 6 if is_selected else 4
                color = "#d04444" if is_selected else "#d89a35"
                canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                   fill=color, outline="white", width=1)
                # Draw a visible preliminary column section, not just a point marker.
                section_cm = self.proposal.metrics.get("reference_column_cm")
                if is_selected and section_cm:
                    half = max(4.0, (section_cm / 100.0) * scale / 2.0)
                    canvas.create_rectangle(x-half, y-half, x+half, y+half,
                                            fill="#e9a2a2", outline="#a52a2a", width=2)
                    canvas.create_text(x+half+4, y-half-3,
                                       text=f"{node.id} · {section_cm}×{section_cm}",
                                       anchor="sw", fill="#7a2020",
                                       font=("Segoe UI", 8, "bold"))
                else:
                    canvas.create_text(x+9, y-9, text=node.id, anchor="sw",
                                       fill="#7a3e16" if is_selected else "#64748b",
                                       font=("Segoe UI", 8, "bold" if is_selected else "normal"))

        canvas.create_text(12, 10, anchor="nw",
                           text=(f"{drawing.name if drawing else 'Sin DXF'} · "
                                 f"Zoom {self._zoom:.2f}× · coordenadas del plano"),
                           fill="#475569", font=("Segoe UI", 9),
                           tags=("viewport_info",))
