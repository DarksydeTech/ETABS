"""Interfaz de propuesta estructural preliminar conectada al analizador DXF."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .structural_design import SYSTEMS, evaluate_alternatives, generate_proposal


class StructuralDesignTab(ttk.Frame):
    def __init__(self, master, architectural_tab, project):
        super().__init__(master, padding=10)
        self.architectural_tab = architectural_tab
        self.project = project
        self.proposal = None
        self.alternatives = []
        self._build()

    def _build(self):
        ttk.Label(self, text="Propuesta estructural automática",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(self, text="Genera candidatos desde los DXF ya importados y clasificados en Continuidad arquitectónica. Revisa y ajusta antes de trasladar elementos a la planta del proyecto.",
                  wraplength=1100).pack(anchor="w", pady=(2, 8))
        controls = ttk.LabelFrame(self, text="Parámetros de interpretación y predimensionamiento", padding=8)
        controls.pack(fill="x", pady=(0, 8))
        self.system = tk.StringVar(value=SYSTEMS[0])
        self.units = tk.StringVar(value="m")
        self.fc = tk.StringVar(value="210")
        self.dead = tk.StringVar(value="6")
        self.live = tk.StringVar(value="2")
        self.tolerance = tk.StringVar(value="0.15")
        self.max_span = tk.StringVar(value="7")
        self.floor = tk.StringVar(value="1")
        fields = [
            ("Sistema", self.system, SYSTEMS, 38),
            ("Unidad DXF", self.units, ("m", "cm", "mm"), 7),
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
            cell.grid(row=row, column=col, sticky="w", padx=5, pady=4)
            ttk.Label(cell, text=label).pack(anchor="w")
            if options:
                ttk.Combobox(cell, textvariable=variable, values=options,
                             state="readonly", width=width).pack(anchor="w")
            else:
                ttk.Entry(cell, textvariable=variable, width=width).pack(anchor="w")
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Generar propuesta y evaluar alternativas",
                   command=self.generate).pack(side="left")
        self.summary = tk.StringVar(value="Importa y clasifica al menos un DXF en la pestaña 8.")
        ttk.Label(actions, textvariable=self.summary).pack(side="left", padx=12)

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        bottom = ttk.Frame(body)
        body.add(top, weight=3)
        body.add(bottom, weight=2)
        self.canvas = tk.Canvas(top, bg="white", highlightthickness=1,
                                highlightbackground="#cbd5e1", height=300)
        self.canvas.pack(fill="both", expand=True)
        tables = ttk.Panedwindow(bottom, orient="horizontal")
        tables.pack(fill="both", expand=True)
        left = ttk.LabelFrame(tables, text="Candidatos de columna", padding=4)
        right = ttk.LabelFrame(tables, text="Vigas y paños preliminares", padding=4)
        tables.add(left, weight=1)
        tables.add(right, weight=1)
        self.nodes = self._tree(left, ("id", "x", "y", "score"), ("ID", "X (m)", "Y (m)", "Puntaje"))
        self.members = self._tree(right, ("id", "length", "section", "kind"),
                                  ("Elemento", "Luz (m)", "Sección guía", "Tipo"))

    @staticmethod
    def _tree(parent, keys, labels):
        tree = ttk.Treeview(parent, columns=keys, show="headings", height=7)
        for key, label in zip(keys, labels):
            tree.heading(key, text=label)
            tree.column(key, width=105, anchor="center")
        tree.pack(fill="both", expand=True)
        return tree

    def generate(self):
        drawings = self.architectural_tab.drawings
        if not drawings:
            messagebox.showinfo("Propuesta estructural", "Primero importa un DXF en Continuidad arquitectónica.", parent=self)
            return
        try:
            number = int(self.floor.get())
            scale = {"m": 1.0, "cm": 0.01, "mm": 0.001}[self.units.get()]
            self.proposal = generate_proposal(
                drawings[0], self.architectural_tab.layer_categories,
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
            self.nodes.insert("", "end", values=(node.id, f"{node.x:.2f}", f"{node.y:.2f}", f"{node.score:.0f}"))
        for beam in self.proposal.beams:
            self.members.insert("", "end", values=(beam.id, f"{beam.length:.2f}",
                                                     f"{beam.width_cm}×{beam.depth_cm} cm", f"Viga {beam.direction}"))
        for slab in self.proposal.slabs:
            self.members.insert("", "end", values=(slab.id, f"{slab.area:.2f} m²",
                                                     f"{slab.width:.2f}×{slab.length:.2f} m",
                                                     slab.behavior))
        self.summary.set(f"{len(self.proposal.nodes)} candidatos · {len(self.proposal.beams)} vigas · {len(self.proposal.slabs)} paños")
        self._draw()
        details = "\n".join(
            f"{item['name']}: {item['candidate_count']} candidatos · {item['beam_count']} vigas · puntaje medio {item['mean_score']} — {item['description']}"
            for item in self.alternatives)
        details += "\n\n" + "\n".join("• " + note for note in self.proposal.notes)
        messagebox.showinfo("Alternativas y criterios", details, parent=self)

    def _draw(self):
        self.canvas.delete("all")
        if not self.proposal or not self.proposal.nodes:
            self.canvas.create_text(20, 20, anchor="nw", text="Sin candidatos para mostrar.", fill="#64748b")
            return
        nodes = self.proposal.nodes
        xmin, xmax = min(n.x for n in nodes), max(n.x for n in nodes)
        ymin, ymax = min(n.y for n in nodes), max(n.y for n in nodes)
        width = max(self.canvas.winfo_width()-50, 100)
        height = max(self.canvas.winfo_height()-50, 100)
        scale = min(width/max(xmax-xmin, 1.0), height/max(ymax-ymin, 1.0))
        ox, oy = 25, 25
        for beam in self.proposal.beams:
            by_id = {n.id:n for n in nodes}
            a, b = by_id[beam.start], by_id[beam.end]
            x1, y1 = ox+(a.x-xmin)*scale, height+oy-(a.y-ymin)*scale
            x2, y2 = ox+(b.x-xmin)*scale, height+oy-(b.y-ymin)*scale
            self.canvas.create_line(x1,y1,x2,y2,fill="#64748b",width=2)
        for node in nodes:
            x, y = ox+(node.x-xmin)*scale, height+oy-(node.y-ymin)*scale
            self.canvas.create_oval(x-4,y-4,x+4,y+4,fill="#c0392b",outline="")
            self.canvas.create_text(x+7,y-7,text=node.id,anchor="sw",font=("Segoe UI",7))
        self.canvas.create_text(10, 8, anchor="nw",
                               text=f"{self.proposal.system} · geometría DXF convertida a m",
                               fill="#475569", font=("Segoe UI", 8))
