"""Interfaz gráfica de ETABS CIXTOP (modelo Python, sin Excel)."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .etabs import EtabsBridge
from .model import Issue, Project, to_float, to_int
from .template import (APP_NAME, APP_VERSION, GEOMETRY_OPTIONS, MODEL_TYPES,
                       SLAB_MOD_LABELS, SLAB_TYPES, WALL_MOD_LABELS)


# --------------------------------------------------------------------------
# Utilidades de interfaz
# --------------------------------------------------------------------------

def fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


class Table(ttk.Frame):
    """Tabla reutilizable con edición por doble clic."""

    def __init__(self, master, columns: list[dict], height: int = 8, on_edit=None):
        super().__init__(master)
        self.columns = columns
        self.on_edit = on_edit
        self.rows: list[dict] = []
        keys = [c["key"] for c in columns]
        self.tree = ttk.Treeview(self, columns=keys, show="headings",
                                 height=height, selectmode="browse")
        ybar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        for column in columns:
            self.tree.heading(column["key"], text=column["label"])
            self.tree.column(column["key"], width=column.get("width", 90),
                             anchor=column.get("anchor", "w"), stretch=False)
        self.tree.bind("<Double-1>", self._edit)
        self.tree.bind("<Return>", self._edit)

    def set_rows(self, rows: list[dict]) -> None:
        self.rows = [dict(row) for row in rows]
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            values = [fmt(row.get(c["key"], "")) for c in self.columns]
            self.tree.insert("", "end", iid=str(index), values=values)

    def selection(self) -> int | None:
        item = self.tree.selection()
        return int(item[0]) if item else None

    def _edit(self, event=None) -> None:
        if event is not None and getattr(event, "y", None) is not None:
            row_id = self.tree.identify_row(event.y)
            column_id = self.tree.identify_column(event.x)
            if not row_id or not column_id:
                return
            self.tree.selection_set(row_id)
        else:
            row_id = self.tree.selection()[0] if self.tree.selection() else None
            column_id = "#1"
        if not row_id:
            return
        index = int(row_id)
        column_index = int(column_id.replace("#", "")) - 1
        if not (0 <= column_index < len(self.columns)):
            return
        column = self.columns[column_index]
        if column.get("readonly"):
            return
        row = self.rows[index]
        old = row.get(column["key"], "")
        value = simpledialog.askstring(
            "Editar", f"{column['label']}\nFila {index + 1}",
            initialvalue=fmt(old), parent=self.winfo_toplevel())
        if value is None:
            return
        value = value.strip()
        if column.get("numeric"):
            if value == "":
                parsed = 0.0
            else:
                try:
                    parsed = float(value.replace(",", "."))
                except ValueError:
                    messagebox.showerror("Valor inválido", f"'{value}' no es un número.")
                    return
        else:
            parsed = value
        if column.get("options") and parsed not in column["options"]:
            messagebox.showerror("Valor inválido",
                                 f"Use uno de: {', '.join(column['options'])}")
            return
        if self.on_edit:
            self.on_edit(index, column["key"], parsed)


def _dialog_text(parent, title: str, text: str) -> None:
    window = tk.Toplevel(parent)
    window.title(title)
    window.geometry("760x460")
    frame = ttk.Frame(window, padding=10)
    frame.pack(fill="both", expand=True)
    box = tk.Text(frame, wrap="word", font=("Consolas", 9))
    bar = ttk.Scrollbar(frame, orient="vertical", command=box.yview)
    box.configure(yscrollcommand=bar.set)
    box.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    box.insert("1.0", text)
    box.configure(state="disabled")


# --------------------------------------------------------------------------
# Aplicación
# --------------------------------------------------------------------------

class EtabsApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION} · Proyecto estructural")
        self.geometry("1360x860")
        self.minsize(1100, 700)
        self.project = Project.new()
        self.bridge = EtabsBridge()
        self._loading = False
        self._build()
        self.refresh_all()
        self._center()

    # -- construcción -----------------------------------------------------
    def _center(self) -> None:
        self.update_idletasks()
        width, height = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - width) // 2
        y = max(0, (self.winfo_screenheight() - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self) -> None:
        self.configure(bg="#f2f4f7")
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#15243a")
        style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"), foreground="#15243a")
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#5b6a7d")
        style.configure("Action.TButton", padding=(9, 5), font=("Segoe UI", 9, "bold"))
        style.configure("Treeview", rowheight=23, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("TNotebook.Tab", padding=(12, 5))

        head = ttk.Frame(self, padding=(18, 12, 18, 4))
        head.pack(fill="x")
        ttk.Label(head, text=APP_NAME, style="Title.TLabel").pack(side="left")
        self.file_label = ttk.Label(head, text="Proyecto nuevo (sin archivo)", style="Sub.TLabel")
        self.file_label.pack(side="left", padx=(14, 0), pady=(8, 0))
        buttons = ttk.Frame(head)
        buttons.pack(side="right")
        for text, command in (("Nuevo", self.new_project),
                              ("Abrir…", self.open_project),
                              ("Guardar…", self.save_project),
                              ("Importar Excel…", self.import_excel)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=3)
        ttk.Button(buttons, text="Validar", style="Action.TButton",
                   command=self.validate).pack(side="left", padx=(10, 3))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(2, 4))
        self.tab_project = ttk.Frame(self.tabs, padding=10)
        self.tab_materials = ttk.Frame(self.tabs, padding=10)
        self.tab_sections = ttk.Frame(self.tabs, padding=10)
        self.tab_areas = ttk.Frame(self.tabs, padding=10)
        self.tab_loads = ttk.Frame(self.tabs, padding=10)
        self.tab_plan = ttk.Frame(self.tabs, padding=10)
        self.tab_etabs = ttk.Frame(self.tabs, padding=10)
        for tab, title in ((self.tab_project, "1 · Proyecto y grillas"),
                           (self.tab_materials, "2 · Materiales"),
                           (self.tab_sections, "3 · Secciones"),
                           (self.tab_areas, "4 · Losas y muros"),
                           (self.tab_loads, "5 · Cargas"),
                           (self.tab_plan, "6 · Planta"),
                           (self.tab_etabs, "7 · ETABS")):
            self.tabs.add(tab, text=title)
        self._build_project_tab()
        self._build_materials_tab()
        self._build_sections_tab()
        self._build_areas_tab()
        self._build_loads_tab()
        self._build_plan_tab()
        self._build_etabs_tab()

        self.status = tk.StringVar(value="Listo")
        ttk.Label(self, textvariable=self.status, anchor="w", relief="groove",
                  padding=(16, 6)).pack(fill="x", side="bottom")

        self.bind("<Control-s>", lambda _e: self.save_project())
        self.bind("<Control-o>", lambda _e: self.open_project())
        self.bind("<Control-n>", lambda _e: self.new_project())

    # -- pestaña proyecto -------------------------------------------------
    def _build_project_tab(self) -> None:
        self.name_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.spacing_x_var = tk.StringVar(value="3")
        self.spacing_y_var = tk.StringVar(value="2")
        form = ttk.Frame(self.tab_project)
        form.pack(fill="x", pady=(0, 8))
        ttk.Label(form, text="Nombre:", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.name_var, width=44).grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(form, text="Descripción:", style="Header.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.desc_var, width=48).grid(row=0, column=3, sticky="w", padx=6)
        self.name_var.trace_add("write", lambda *_: self._apply_header())
        self.desc_var.trace_add("write", lambda *_: self._apply_header())

        body = ttk.Frame(self.tab_project)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="c")
        body.columnconfigure(1, weight=1, uniform="c")
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)

        # Niveles
        levels = ttk.LabelFrame(body, text=" Niveles ", padding=8)
        levels.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        self.story_count = tk.IntVar(value=12)
        self.story_typical = tk.StringVar(value="2.8")
        self.story_first = tk.StringVar(value="3.0")
        row = ttk.Frame(levels)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="Cantidad:").pack(side="left")
        ttk.Spinbox(row, from_=1, to=50, width=5, textvariable=self.story_count).pack(side="left", padx=(4, 12))
        ttk.Label(row, text="Altura típica:").pack(side="left")
        ttk.Entry(row, width=7, textvariable=self.story_typical).pack(side="left", padx=(4, 12))
        ttk.Label(row, text="Primer nivel:").pack(side="left")
        ttk.Entry(row, width=7, textvariable=self.story_first).pack(side="left", padx=(4, 12))
        ttk.Button(row, text="Generar niveles", style="Action.TButton",
                   command=self.generate_stories).pack(side="left")
        self.story_table = Table(levels, [
            {"key": "name", "label": "Story ID", "width": 150},
            {"key": "height", "label": "Altura (m)", "width": 100, "numeric": True, "anchor": "e"},
            {"key": "elevation", "label": "Elevación (m)", "width": 110, "readonly": True, "anchor": "e"},
        ], height=8, on_edit=self._edit_story)
        self.story_table.pack(fill="both", expand=True)

        # Grillas X e Y
        grids = ttk.LabelFrame(body, text=" Grillas cartesianas ", padding=8)
        grids.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        for axis, row_index in (("X", 0), ("Y", 1)):
            frame = ttk.Frame(grids)
            frame.pack(fill="both", expand=True, pady=2)
            bar = ttk.Frame(frame)
            bar.pack(fill="x")
            ttk.Label(bar, text=f"Grillas {axis}:", style="Header.TLabel").pack(side="left")
            count_var = tk.IntVar(value=3 if axis == "X" else 5)
            spacing_var = self.spacing_x_var if axis == "X" else self.spacing_y_var
            ttk.Spinbox(bar, from_=2, to=50, width=4, textvariable=count_var).pack(side="left", padx=4)
            ttk.Label(bar, text="separación:").pack(side="left")
            ttk.Entry(bar, width=6, textvariable=spacing_var).pack(side="left", padx=(3, 6))
            ttk.Button(bar, text="Generar", command=lambda a=axis: self.generate_grids(a)).pack(side="left")
            ttk.Button(bar, text="+ Añadir", command=lambda a=axis: self.add_grid(a)).pack(side="left", padx=3)
            if axis == "X":
                self.grid_x_count, self.grid_x_spacing = count_var, spacing_var
            else:
                self.grid_y_count, self.grid_y_spacing = count_var, spacing_var
            table = Table(frame, [
                {"key": "id", "label": "Grid ID", "width": 70},
                {"key": "coord", "label": "Coord (m)", "width": 90, "numeric": True, "anchor": "e"},
                {"key": "spacing", "label": "Separación (m)", "width": 100, "readonly": True, "anchor": "e"},
            ], height=5, on_edit=lambda i, k, v, a=axis: self._edit_grid(a, i, k, v))
            table.pack(fill="both", expand=True)
            if axis == "X":
                self.grid_x_table = table
            else:
                self.grid_y_table = table

        # Inclinadas
        inclined = ttk.LabelFrame(body, text=" Grillas inclinadas ", padding=8)
        inclined.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        columns = [("x", "Tipo 1 (X1 abajo → X2 arriba)"),
                   ("y", "Tipo 2 (Y1 izquierda → Y2 derecha)")]
        for index, (axis, title) in enumerate(columns):
            frame = ttk.Frame(inclined)
            frame.grid(row=0, column=index, sticky="nsew", padx=(0, 8) if index == 0 else (8, 0))
            inclined.columnconfigure(index, weight=1)
            header = ttk.Frame(frame)
            header.pack(fill="x")
            ttk.Label(header, text=title, style="Header.TLabel").pack(side="left")
            ttk.Button(header, text="+ Añadir", command=lambda a=axis: self.add_inclined(a)).pack(side="right")
            ttk.Button(header, text="Eliminar", command=lambda a=axis: self.remove_inclined(a)).pack(side="right", padx=4)
            table = Table(frame, [
                {"key": "id", "label": "ID", "width": 70},
                {"key": "start", "label": "Inicio (m)", "width": 95, "numeric": True, "anchor": "e"},
                {"key": "end", "label": "Fin (m)", "width": 95, "numeric": True, "anchor": "e"},
            ], height=4, on_edit=lambda i, k, v, a=axis: self._edit_inclined(a, i, k, v))
            table.pack(fill="both", expand=True)
            if axis == "x":
                self.inclined_table_x = table
            else:
                self.inclined_table_y = table

    # -- materiales -------------------------------------------------------
    def _build_materials_tab(self) -> None:
        bar = ttk.Frame(self.tab_materials)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Biblioteca de materiales (kgf/cm², t/m³)",
                  style="Header.TLabel").pack(side="left")
        ttk.Button(bar, text="+ Material", command=self.add_material).pack(side="right")
        ttk.Button(bar, text="Eliminar", command=self.remove_material).pack(side="right", padx=4)
        self.material_table = Table(self.tab_materials, [
            {"key": "name", "label": "Nombre", "width": 240},
            {"key": "kind", "label": "Tipo", "width": 95,
             "options": ["Concrete", "Rebar", "Tendon", "Steel", "Masonry"]},
            {"key": "fc", "label": "fc", "width": 70, "numeric": True, "anchor": "e"},
            {"key": "fy", "label": "Fy", "width": 75, "numeric": True, "anchor": "e"},
            {"key": "fm", "label": "fm", "width": 70, "numeric": True, "anchor": "e"},
            {"key": "E", "label": "E", "width": 95, "numeric": True, "anchor": "e"},
            {"key": "weight", "label": "Peso t/m³", "width": 85, "numeric": True, "anchor": "e"},
            {"key": "poisson", "label": "Poisson", "width": 75, "numeric": True, "anchor": "e"},
        ], height=20, on_edit=self._edit_material)
        self.material_table.pack(fill="both", expand=True)

    # -- secciones --------------------------------------------------------
    def _build_sections_tab(self) -> None:
        counts = ttk.LabelFrame(self.tab_sections, text=" Cantidad por tipo de sección ")
        counts.pack(fill="x", pady=(0, 8))
        self.count_vars: dict[str, tk.IntVar] = {}
        labels = [("vs_conc", "VS Concreto"), ("vp_conc", "VP Concreto"),
                  ("vb_conc", "VB Concreto"), ("col_conc", "Columnas concreto"),
                  ("vp_steel_i", "VP acero I"), ("vs_steel_i", "VS acero I"),
                  ("vs_hss", "VS HSS"), ("col_steel_i", "Col. acero I"),
                  ("col_hss", "Col. HSS")]
        for index, (key, label) in enumerate(labels):
            ttk.Label(counts, text=label).grid(row=index // 5, column=(index % 5) * 2,
                                                sticky="w", padx=(8, 3), pady=3)
            var = tk.IntVar(value=0)
            self.count_vars[key] = var
            ttk.Spinbox(counts, from_=0, to=50, width=5, textvariable=var).grid(
                row=index // 5, column=(index % 5) * 2 + 1, sticky="w", padx=(0, 12))
        ttk.Button(counts, text="Generar secciones", style="Action.TButton",
                   command=self.generate_sections).grid(row=0, column=10, rowspan=2, padx=14)
        ttk.Button(counts, text="Eliminar seleccionada",
                   command=self.remove_section).grid(row=2, column=10, pady=4)
        self.section_table = Table(self.tab_sections, [
            {"key": "name", "label": "Nombre", "width": 150},
            {"key": "material", "label": "Material", "width": 165},
            {"key": "element", "label": "Elemento", "width": 120},
            {"key": "geometry", "label": "Geometría", "width": 120, "options": GEOMETRY_OPTIONS},
            {"key": "d", "label": "d cm", "width": 65, "numeric": True, "anchor": "e"},
            {"key": "bf", "label": "bf cm", "width": 65, "numeric": True, "anchor": "e"},
            {"key": "tw", "label": "tw cm", "width": 65, "numeric": True, "anchor": "e"},
            {"key": "tf", "label": "tf cm", "width": 65, "numeric": True, "anchor": "e"},
            {"key": "f22", "label": "f22", "width": 60, "numeric": True, "anchor": "e"},
            {"key": "f33", "label": "f33", "width": 60, "numeric": True, "anchor": "e"},
            {"key": "area", "label": "Área cm²", "width": 85, "readonly": True, "anchor": "e"},
            {"key": "inertia", "label": "I33 cm⁴", "width": 100, "readonly": True, "anchor": "e"},
        ], height=20, on_edit=self._edit_section)
        self.section_table.pack(fill="both", expand=True)

    # -- losas y muros ----------------------------------------------------
    def _build_areas_tab(self) -> None:
        notebook = ttk.Notebook(self.tab_areas)
        notebook.pack(fill="both", expand=True)
        slab_tab = ttk.Frame(notebook, padding=6)
        wall_tab = ttk.Frame(notebook, padding=6)
        notebook.add(slab_tab, text="Losas")
        notebook.add(wall_tab, text="Muros")

        slab_columns = [
            {"key": "name", "label": "Nombre", "width": 130},
            {"key": "material", "label": "Material", "width": 165},
            {"key": "model_type", "label": "Modeling", "width": 110, "options": MODEL_TYPES},
            {"key": "slab_type", "label": "Slab type", "width": 100, "options": SLAB_TYPES},
            {"key": "thickness", "label": "e cm", "width": 65, "numeric": True, "anchor": "e"},
        ] + [{"key": f"mod{i}", "label": label, "width": 65, "numeric": True, "anchor": "e"}
             for i, label in enumerate(SLAB_MOD_LABELS)]
        self.slab_table = Table(slab_tab, slab_columns, height=12,
                                on_edit=lambda i, k, v: self._edit_area("slab", i, k, v))
        self.slab_table.pack(fill="both", expand=True)
        ttk.Button(slab_tab, text="+ Losa", command=lambda: self.add_area("slab")).pack(anchor="w", pady=6)

        wall_columns = [
            {"key": "name", "label": "Nombre", "width": 130},
            {"key": "material", "label": "Material", "width": 165},
            {"key": "model_type", "label": "Modeling", "width": 110, "options": MODEL_TYPES},
            {"key": "thickness", "label": "e cm", "width": 65, "numeric": True, "anchor": "e"},
        ] + [{"key": f"mod{i}", "label": label, "width": 65, "numeric": True, "anchor": "e"}
             for i, label in enumerate(WALL_MOD_LABELS)]
        self.wall_table = Table(wall_tab, wall_columns, height=12,
                                on_edit=lambda i, k, v: self._edit_area("wall", i, k, v))
        self.wall_table.pack(fill="both", expand=True)
        ttk.Button(wall_tab, text="+ Muro", command=lambda: self.add_area("wall")).pack(anchor="w", pady=6)

    # -- cargas -----------------------------------------------------------
    def _build_loads_tab(self) -> None:
        notebook = ttk.Notebook(self.tab_loads)
        notebook.pack(fill="both", expand=True)
        patterns_tab = ttk.Frame(notebook, padding=8)
        seismic_tab = ttk.Frame(notebook, padding=8)
        mass_tab = ttk.Frame(notebook, padding=8)
        combos_tab = ttk.Frame(notebook, padding=8)
        notebook.add(patterns_tab, text="Patrones")
        notebook.add(seismic_tab, text="Sismo E.030")
        notebook.add(mass_tab, text="Fuente de masa")
        notebook.add(combos_tab, text="Combinaciones")

        bar = ttk.Frame(patterns_tab)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="+ Patrón", command=self.add_pattern).pack(side="left")
        ttk.Button(bar, text="Eliminar", command=self.remove_pattern).pack(side="left", padx=4)
        ttk.Button(bar, text="Restaurar plantilla", command=self.restore_loads).pack(side="right")
        self.pattern_table = Table(patterns_tab, [
            {"key": "name", "label": "Nombre", "width": 120},
            {"key": "type", "label": "Tipo", "width": 110,
             "options": ["Dead", "SuperDead", "Live", "ReduceLive", "Quake",
                         "Wind", "Snow", "RoofLive", "Other"]},
            {"key": "self_weight", "label": "Peso propio", "width": 95, "numeric": True, "anchor": "e"},
            {"key": "description", "label": "Descripción", "width": 520},
        ], height=12, on_edit=self._edit_pattern)
        self.pattern_table.pack(fill="both", expand=True)

        # Sismo
        self.seismic_vars = {key: tk.StringVar() for key in
                             ("Z", "U", "S", "Tp", "TL", "R", "T", "eccentricity")}
        form = ttk.Frame(seismic_tab)
        form.pack(fill="x")
        labels = {"Z": "Z (zona)", "U": "U (categoría)", "S": "S (suelo)",
                  "Tp": "Tp (s)", "TL": "TL (s)", "R": "R", "T": "T (s)",
                  "eccentricity": "Excentricidad"}
        for index, (key, label) in enumerate(labels.items()):
            ttk.Label(form, text=label).grid(row=index // 4, column=(index % 4) * 2,
                                             sticky="w", padx=(0, 4), pady=4)
            entry = ttk.Entry(form, width=9, textvariable=self.seismic_vars[key])
            entry.grid(row=index // 4, column=(index % 4) * 2 + 1, sticky="w", padx=(0, 18))
            entry.bind("<FocusOut>", lambda _e, k=key: self._apply_seismic(k))
        self.seismic_result = ttk.Label(seismic_tab, text="", style="Sub.TLabel")
        self.seismic_result.pack(anchor="w", pady=(6, 2))
        self.seismic_pattern_table = Table(seismic_tab, [
            {"key": "name", "label": "Patrón", "width": 100},
            {"key": "direction", "label": "Dirección", "width": 90,
             "options": ["X", "Y"]},
            {"key": "lateral", "label": "Carga lateral", "width": 180},
        ], height=5, on_edit=self._edit_seismic_pattern)
        self.seismic_pattern_table.pack(fill="both", expand=True, pady=6)
        ttk.Button(seismic_tab, text="Actualizar coeficiente", command=self.update_seismic).pack(anchor="w")

        # Masa
        self.mass_vars = {key: tk.BooleanVar() for key in
                          ("include_self", "include_added", "include_loads")}
        self.mass_name = tk.StringVar()
        row = ttk.Frame(mass_tab)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Nombre:").pack(side="left")
        ttk.Entry(row, width=20, textvariable=self.mass_name).pack(side="left", padx=6)
        self.mass_name.trace_add("write", lambda *_: self._apply_mass_name())
        for key, label in (("include_self", "Element Self Mass"),
                           ("include_added", "Additional Mass"),
                           ("include_loads", "Specified Loads")):
            ttk.Checkbutton(row, text=label, variable=self.mass_vars[key],
                            command=self._apply_mass_flags).pack(side="left", padx=8)
        ttk.Button(row, text="+ Fila", command=self.add_mass_factor).pack(side="right")
        ttk.Button(row, text="Eliminar", command=self.remove_mass_factor).pack(side="right", padx=4)
        self.mass_table = Table(mass_tab, [
            {"key": "pattern", "label": "Load Pattern", "width": 180},
            {"key": "factor", "label": "Factor", "width": 100, "numeric": True, "anchor": "e"},
        ], height=8, on_edit=self._edit_mass_factor)
        self.mass_table.pack(fill="both", expand=True, pady=6)

        # Combinaciones
        bar = ttk.Frame(combos_tab)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="+ Combinación", command=self.add_combo).pack(side="left")
        ttk.Button(bar, text="Eliminar", command=self.remove_combo).pack(side="left", padx=4)
        ttk.Label(bar, text="Factores: escriba CM:1.4, CV:1.7",
                  style="Sub.TLabel").pack(side="right")
        self.combo_table = Table(combos_tab, [
            {"key": "name", "label": "Nombre", "width": 190},
            {"key": "type", "label": "Tipo", "width": 110,
             "options": ["Linear Add", "Envelope"]},
            {"key": "factors_text", "label": "Factores", "width": 430},
            {"key": "notes", "label": "Notas", "width": 220},
        ], height=14, on_edit=self._edit_combo)
        self.combo_table.pack(fill="both", expand=True)

    # -- planta -----------------------------------------------------------
    def _build_plan_tab(self) -> None:
        bar = ttk.Frame(self.tab_plan)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Regenerar planta", style="Action.TButton",
                   command=self.regenerate_plan).pack(side="left")
        ttk.Label(bar, text="Ver:", style="Header.TLabel").pack(side="left", padx=(16, 4))
        self.plan_view = tk.StringVar(value="Columnas")
        combo = ttk.Combobox(bar, textvariable=self.plan_view, state="readonly", width=18,
                             values=["Columnas", "Vigas X", "Vigas Y",
                                     "Vigas inclinadas T1", "Vigas inclinadas T2",
                                     "Muros", "Losas"])
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._fill_plan_table())
        self.plan_summary = ttk.Label(bar, text="", style="Sub.TLabel")
        self.plan_summary.pack(side="right")

        paned = ttk.Panedwindow(self.tab_plan, orient="vertical")
        paned.pack(fill="both", expand=True)
        canvas_frame = ttk.Frame(paned)
        self.canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=1,
                                highlightbackground="#d5dce8", height=360)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.draw_plan())
        paned.add(canvas_frame, weight=3)
        table_frame = ttk.Frame(paned)
        self.plan_table = Table(table_frame, [], height=7, on_edit=self._edit_plan_row)
        self.plan_table.pack(fill="both", expand=True)
        paned.add(table_frame, weight=2)

    # -- ETABS ------------------------------------------------------------
    def _build_etabs_tab(self) -> None:
        bar = ttk.Frame(self.tab_etabs)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Conectar ETABS", command=self.connect_etabs).pack(side="left")
        ttk.Button(bar, text="Nuevo modelo ETABS", command=self.initialize_etabs).pack(side="left", padx=6)
        self.clean_model = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Borrar barras y áreas antes de dibujar",
                        variable=self.clean_model).pack(side="left", padx=12)
        self.etabs_state = ttk.Label(bar, text="Sin conexión", style="Sub.TLabel")
        self.etabs_state.pack(side="right")

        actions = ttk.LabelFrame(self.tab_etabs, text=" Exportaciones ", padding=8)
        actions.pack(fill="x")
        buttons = [
            ("Niveles", lambda: self.export_one("niveles", self.bridge.export_stories)),
            ("Grillas", lambda: self.export_one("grillas", self.bridge.export_grids)),
            ("Materiales", lambda: self.export_one("materiales", self.bridge.export_materials)),
            ("Secciones", lambda: self.export_one("secciones", self.bridge.export_sections)),
            ("Losas y muros", lambda: self.export_one("áreas", self.bridge.export_area_sections)),
            ("Cargas y combos", lambda: self.export_one("cargas", self.bridge.export_loads)),
            ("Dibujar planta", self.export_plan),
        ]
        for index, (label, command) in enumerate(buttons):
            ttk.Button(actions, text=label, style="Action.TButton",
                       command=command).grid(row=index // 4, column=index % 4,
                                             sticky="w", padx=4, pady=4)
        ttk.Button(actions, text="Exportar todo el modelo", style="Action.TButton",
                   command=self.export_all).grid(row=1, column=1, columnspan=2, sticky="w", padx=4, pady=4)
        ttk.Label(self.tab_etabs,
                  text="Secuencia recomendada: materiales → secciones → áreas → cargas → grillas → niveles → planta. "
                       "Revisa unidades (Ton, m, C) y guarda el modelo ETABS antes de limpiar objetos.",
                  wraplength=1100, style="Sub.TLabel").pack(anchor="w", pady=(8, 4))
        self.log = tk.Text(self.tab_etabs, height=16, wrap="word", font=("Consolas", 9),
                           state="disabled", bg="#f8fafc", relief="flat")
        self.log.pack(fill="both", expand=True)

    # -- sincronización ---------------------------------------------------
    def refresh_all(self) -> None:
        self._loading = True
        project = self.project
        self.name_var.set(project.name)
        self.desc_var.set(project.description)
        self.story_count.set(len(project.stories))
        if project.stories:
            self.story_typical.set(fmt(project.stories[-1]["height"]))
            self.story_first.set(fmt(project.stories[0]["height"]))
        self.spacing_x_var.set(fmt(project.spacing_x))
        self.spacing_y_var.set(fmt(project.spacing_y))
        self.grid_x_count.set(len(project.grid_x))
        self.grid_y_count.set(len(project.grid_y))
        for key, var in self.count_vars.items():
            var.set(int(project.section_counts.get(key, 0)))
        for key, var in self.seismic_vars.items():
            var.set(fmt(project.seismic.get(key, "")))
        self.mass_name.set(project.mass_source.get("name", "MsSrc1"))
        for key, var in self.mass_vars.items():
            var.set(bool(project.mass_source.get(key, False)))
        self.story_table.set_rows(project.stories)
        self.grid_x_table.set_rows(project.grid_x)
        self.grid_y_table.set_rows(project.grid_y)
        self.inclined_table_x.set_rows(project.inclined_x)
        self.inclined_table_y.set_rows(project.inclined_y)
        self.material_table.set_rows(project.materials)
        self.section_table.set_rows(project.frame_sections)
        self.slab_table.set_rows([self._area_row(s, "slab") for s in project.slabs])
        self.wall_table.set_rows([self._area_row(w, "wall") for w in project.walls])
        self.pattern_table.set_rows(project.patterns)
        self.seismic_pattern_table.set_rows(project.seismic.get("patterns", []))
        self.mass_table.set_rows(project.mass_source.get("factors", []))
        self.combo_table.set_rows([{**c, "factors_text": self._factors_text(c)}
                                   for c in project.combos])
        self._fill_plan_table()
        self.draw_plan()
        self.update_seismic()
        self.file_label.configure(
            text=str(project.path) if project.path else "Proyecto nuevo (sin archivo)")
        self._loading = False
        self.status.set(project.plan.summary())

    @staticmethod
    def _area_row(item: dict, kind: str) -> dict:
        row = {key: item.get(key, "") for key in
               ("name", "material", "model_type", "slab_type", "thickness")}
        for index, value in enumerate(item.get("mods", [])):
            row[f"mod{index}"] = value
        return row

    @staticmethod
    def _factors_text(combo: dict) -> str:
        return ", ".join(f"{case}:{fmt(factor)}"
                         for case, factor in combo.get("factors", {}).items())

    @staticmethod
    def _parse_factors(text: str) -> dict:
        factors = {}
        for chunk in str(text).split(","):
            if ":" not in chunk:
                continue
            case, value = chunk.split(":", 1)
            case = case.strip()
            if case:
                try:
                    factors[case] = float(value.replace(",", ".").strip())
                except ValueError:
                    continue
        return factors

    # -- proyecto / historias / grillas ----------------------------------
    def _apply_header(self) -> None:
        if self._loading:
            return
        self.project.name = self.name_var.get()
        self.project.description = self.desc_var.get()
        self.project.dirty = True

    def generate_stories(self) -> None:
        try:
            count = self.project.generate_stories(
                self.story_count.get(), to_float(self.story_typical.get(), 2.8),
                to_float(self.story_first.get(), 3.0))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Niveles", str(exc))
            return
        self.refresh_all()
        self.status.set(f"{count} niveles generados.")

    def _edit_story(self, index: int, key: str, value) -> None:
        story = self.project.stories[index]
        story[key] = value
        elevation = 0.0
        for item in self.project.stories:
            elevation += to_float(item["height"])
            item["elevation"] = elevation
        self.project.dirty = True
        self.refresh_all()

    def generate_grids(self, axis: str) -> None:
        try:
            if axis == "X":
                self.project.spacing_x = to_float(self.grid_x_spacing.get(), 3.0)
                count = self.grid_x_count.get()
                self.project.grid_x = [{"id": _grid_id("X", i), "coord": (i - 1) * self.project.spacing_x,
                                        "spacing": 0.0} for i in range(1, count + 1)]
            else:
                self.project.spacing_y = to_float(self.grid_y_spacing.get(), 2.0)
                count = self.grid_y_count.get()
                self.project.grid_y = [{"id": _grid_id("Y", i), "coord": (i - 1) * self.project.spacing_y,
                                        "spacing": 0.0} for i in range(1, count + 1)]
            self.project.generate_plan()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Grillas", str(exc))
            return
        self.refresh_all()
        self.status.set(f"Grillas {axis} regeneradas.")

    def add_grid(self, axis: str) -> None:
        try:
            self.project.add_grid(axis)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Grillas", str(exc))
            return
        self.refresh_all()

    def _grid_list(self, axis: str):
        return self.project.grid_x if axis == "X" else self.project.grid_y

    def _edit_grid(self, axis: str, index: int, key: str, value) -> None:
        grid = self._grid_list(axis)[index]
        grid[key] = value
        self.project.grid_assignments()
        self.project.generate_plan()
        self.refresh_all()

    def add_inclined(self, axis: str) -> None:
        target = self.project.inclined_x if axis == "x" else self.project.inclined_y
        prefix = "I" if axis == "x" else "J"
        number = 1
        ids = {str(item.get("id")) for item in self.project.inclined_x + self.project.inclined_y}
        while f"{prefix}{number}" in ids:
            number += 1
        target.append({"id": f"{prefix}{number}", "start": 0.0, "end": 1.0})
        self.project.generate_plan()
        self.refresh_all()

    def remove_inclined(self, axis: str) -> None:
        table = self.inclined_table_x if axis == "x" else self.inclined_table_y
        index = table.selection()
        target = self.project.inclined_x if axis == "x" else self.project.inclined_y
        if index is None or index >= len(target):
            return
        target.pop(index)
        self.project.generate_plan()
        self.refresh_all()

    def _edit_inclined(self, axis: str, index: int, key: str, value) -> None:
        target = self.project.inclined_x if axis == "x" else self.project.inclined_y
        target[index][key] = value
        self.project.generate_plan()
        self.refresh_all()

    # -- materiales -------------------------------------------------------
    def _edit_material(self, index: int, key: str, value) -> None:
        self.project.materials[index][key] = value
        if key in ("fc", "fy", "fm"):
            material = self.project.materials[index]
            if material.get("kind") == "Concrete":
                material["E"] = max(1.0, 15000.0 * (to_float(material.get("fc")) ** 0.5))
            elif material.get("kind") == "Masonry":
                material["E"] = 500.0 * to_float(material.get("fm"))
        self.project.dirty = True
        self.refresh_all()

    def add_material(self) -> None:
        self.project.materials.append({"name": "Material nuevo", "kind": "Concrete",
                                       "fc": 210.0, "fy": 0.0, "fm": 0.0,
                                       "E": 217000.0, "weight": 2.4, "poisson": 0.2})
        self.project.dirty = True
        self.refresh_all()

    def remove_material(self) -> None:
        index = self.material_table.selection()
        if index is None:
            return
        used = {s.get("material") for s in self.project.frame_sections}
        used |= {s.get("material") for s in self.project.slabs + self.project.walls}
        name = self.project.materials[index].get("name")
        if name in used:
            messagebox.showwarning("Material en uso", "El material está asignado a una sección.")
            return
        self.project.materials.pop(index)
        self.project.dirty = True
        self.refresh_all()

    # -- secciones --------------------------------------------------------
    def generate_sections(self) -> None:
        for key, var in self.count_vars.items():
            self.project.section_counts[key] = var.get()
        count = self.project.generate_frame_sections()
        self.refresh_all()
        self.status.set(f"{count} secciones generadas.")

    def _edit_section(self, index: int, key: str, value) -> None:
        section = self.project.frame_sections[index]
        section[key] = value
        self.project.refresh_section_properties()
        self.project.generate_plan()
        self.refresh_all()

    def remove_section(self) -> None:
        index = self.section_table.selection()
        if index is None:
            return
        self.project.frame_sections.pop(index)
        self.project._prune_assignments()
        self.project.generate_plan()
        self.project.dirty = True
        self.refresh_all()

    # -- áreas ------------------------------------------------------------
    def _edit_area(self, kind: str, index: int, key: str, value) -> None:
        collection = self.project.slabs if kind == "slab" else self.project.walls
        item = collection[index]
        if key.startswith("mod"):
            mods = item.setdefault("mods", [1.0] * 7)
            mod_index = int(key[3:])
            while len(mods) <= mod_index:
                mods.append(1.0)
            mods[mod_index] = value
        else:
            item[key] = value
        self.project.dirty = True
        self.project.generate_plan()
        self.refresh_all()

    def add_area(self, kind: str) -> None:
        if kind == "slab":
            self.project.slabs.append({"name": f"Losa_{len(self.project.slabs) + 1}",
                                       "material": "Concreto fc 280", "model_type": "Shell-Thin",
                                       "slab_type": "Slab", "thickness": 20.0, "mods": [1.0] * 7})
        else:
            self.project.walls.append({"name": f"Wall_{len(self.project.walls) + 1}",
                                       "material": "Concreto fc 280", "model_type": "Shell-Thick",
                                       "thickness": 20.0, "mods": [1.0, 1.0, 1.0, 0.6, 0.6, 0.6, 1.0]})
        self.project.dirty = True
        self.project.generate_plan()
        self.refresh_all()

    # -- cargas -----------------------------------------------------------
    def _edit_pattern(self, index: int, key: str, value) -> None:
        self.project.patterns[index][key] = value
        self.project.dirty = True
        self.refresh_all()

    def add_pattern(self) -> None:
        self.project.patterns.append({"name": "PAT", "type": "Dead", "self_weight": 0.0,
                                      "description": ""})
        self.project.dirty = True
        self.refresh_all()

    def remove_pattern(self) -> None:
        index = self.pattern_table.selection()
        if index is None:
            return
        self.project.patterns.pop(index)
        self.project.dirty = True
        self.refresh_all()

    def _apply_seismic(self, key: str) -> None:
        if self._loading:
            return
        self.project.seismic[key] = to_float(self.seismic_vars[key].get(), 0.0)
        self.update_seismic()
        self.project.dirty = True

    def update_seismic(self) -> None:
        from .template import seismic_coefficient, seismic_k
        coefficient = seismic_coefficient(self.project.seismic)
        k = seismic_k(self.project.seismic)
        self.seismic_result.configure(
            text=f"ZUCS/R = {coefficient:.4f}    K = {k:.3f}")

    def _edit_seismic_pattern(self, index: int, key: str, value) -> None:
        self.project.seismic["patterns"][index][key] = value
        self.project.dirty = True
        self.refresh_all()

    def _apply_mass_name(self) -> None:
        if not self._loading:
            self.project.mass_source["name"] = self.mass_name.get().strip() or "MsSrc1"
            self.project.dirty = True

    def _apply_mass_flags(self) -> None:
        if self._loading:
            return
        for key, var in self.mass_vars.items():
            self.project.mass_source[key] = bool(var.get())
        self.project.dirty = True

    def _edit_mass_factor(self, index: int, key: str, value) -> None:
        self.project.mass_source["factors"][index][key] = value
        self.project.dirty = True
        self.refresh_all()

    def add_mass_factor(self) -> None:
        self.project.mass_source.setdefault("factors", []).append(
            {"pattern": "CM", "factor": 1.0})
        self.project.dirty = True
        self.refresh_all()

    def remove_mass_factor(self) -> None:
        index = self.mass_table.selection()
        if index is None:
            return
        factors = self.project.mass_source.get("factors", [])
        if index < len(factors):
            factors.pop(index)
        self.project.dirty = True
        self.refresh_all()

    def _edit_combo(self, index: int, key: str, value) -> None:
        combo = self.project.combos[index]
        if key == "factors_text":
            combo["factors"] = self._parse_factors(value)
        else:
            combo[key] = value
        self.project.dirty = True
        self.refresh_all()

    def add_combo(self) -> None:
        self.project.combos.append({"name": "COMBO", "type": "Linear Add",
                                    "factors": {"CM": 1.0}, "notes": ""})
        self.project.dirty = True
        self.refresh_all()

    def remove_combo(self) -> None:
        index = self.combo_table.selection()
        if index is None:
            return
        self.project.combos.pop(index)
        self.project.dirty = True
        self.refresh_all()

    def restore_loads(self) -> None:
        if messagebox.askyesno("Restaurar cargas",
                               "Se reemplazarán patrones, sismo, masa y combinaciones por la plantilla."):
            self.project.generate_loads()
            self.refresh_all()

    # -- planta -----------------------------------------------------------
    def regenerate_plan(self) -> None:
        self.project.generate_plan()
        self.refresh_all()

    def _fill_plan_table(self) -> None:
        if not hasattr(self, "plan_table"):
            return
        view = self.plan_view.get()
        plan = self.project.plan
        if view == "Columnas":
            columns = [{"key": "id", "label": "ID", "width": 90, "readonly": True},
                       {"key": "kind", "label": "Tipo", "width": 90, "readonly": True},
                       {"key": "x", "label": "X", "width": 80, "readonly": True, "anchor": "e"},
                       {"key": "y", "label": "Y", "width": 80, "readonly": True, "anchor": "e"},
                       {"key": "section", "label": "Sección", "width": 180},
                       {"key": "angle", "label": "Giro (°)", "width": 80, "numeric": True, "anchor": "e"}]
            rows = [{"id": c.id, "kind": c.kind, "x": c.x, "y": c.y,
                     "section": c.section, "angle": c.angle} for c in plan.columns]
            kind = "column"
        elif view.startswith("Vigas"):
            beams = {"Vigas X": plan.beams_x, "Vigas Y": plan.beams_y,
                     "Vigas inclinadas T1": plan.beams_i1,
                     "Vigas inclinadas T2": plan.beams_i2}[view]
            columns = [{"key": "id", "label": "ID", "width": 100, "readonly": True},
                       {"key": "grid", "label": "Grilla", "width": 80, "readonly": True},
                       {"key": "col_a", "label": "Col A", "width": 90, "readonly": True},
                       {"key": "col_b", "label": "Col B", "width": 90, "readonly": True},
                       {"key": "x", "label": "X centro", "width": 90, "readonly": True, "anchor": "e"},
                       {"key": "y", "label": "Y centro", "width": 90, "readonly": True, "anchor": "e"},
                       {"key": "section", "label": "Sección", "width": 190}]
            rows = [{"id": b.id, "grid": b.grid, "col_a": b.col_a, "col_b": b.col_b,
                     "x": b.x, "y": b.y, "section": b.section} for b in beams]
            kind = "beam"
        elif view == "Muros":
            columns = [{"key": "id", "label": "ID", "width": 90, "readonly": True},
                       {"key": "col_a", "label": "Columna A", "width": 110},
                       {"key": "col_b", "label": "Columna B", "width": 110},
                       {"key": "length", "label": "Longitud", "width": 90, "readonly": True, "anchor": "e"},
                       {"key": "section", "label": "Sección", "width": 170}]
            rows = [{"id": w.id, "col_a": w.col_a, "col_b": w.col_b,
                     "length": w.length, "section": w.section} for w in plan.walls]
            kind = "wall"
        else:
            columns = [{"key": "id", "label": "ID", "width": 100, "readonly": True},
                       {"key": "vertices", "label": "Vértices", "width": 330, "readonly": True},
                       {"key": "x", "label": "X centro", "width": 90, "readonly": True, "anchor": "e"},
                       {"key": "y", "label": "Y centro", "width": 90, "readonly": True, "anchor": "e"},
                       {"key": "section", "label": "Sección", "width": 160}]
            rows = [{"id": s.id, "vertices": ", ".join(s.vertex_ids),
                     "x": s.centroid[0], "y": s.centroid[1], "section": s.section}
                    for s in plan.slabs]
            kind = "slab"
        self.plan_table.columns = columns
        self.plan_table.tree.configure(columns=[c["key"] for c in columns])
        for column in columns:
            self.plan_table.tree.heading(column["key"], text=column["label"])
            self.plan_table.tree.column(column["key"], width=column.get("width", 90),
                                        anchor=column.get("anchor", "w"), stretch=False)
        self.plan_table.kind = kind
        self.plan_table.set_rows(rows)
        self.plan_summary.configure(text=plan.summary())

    def _edit_plan_row(self, index: int, key: str, value) -> None:
        kind = getattr(self.plan_table, "kind", "")
        plan = self.project.plan
        if kind == "column":
            column = plan.columns[index]
            if key == "section":
                column.section = value
                self.project.assignments["column_sections"][column.id] = value
            elif key == "angle":
                column.angle = value
        elif kind == "beam":
            view = self.plan_view.get()
            beams = {"Vigas X": plan.beams_x, "Vigas Y": plan.beams_y,
                     "Vigas inclinadas T1": plan.beams_i1,
                     "Vigas inclinadas T2": plan.beams_i2}[view]
            beam = beams[index]
            beam.section = value
            self.project.assignments["beam_sections"][beam.id] = value
        elif kind == "wall":
            definitions = [{"id": w.id, "a": w.col_a, "b": w.col_b, "section": w.section}
                           for w in plan.walls]
            definitions[index][{"col_a": "a", "col_b": "b"}.get(key, key)] = value
            self.project.set_wall_definitions(definitions)
        elif kind == "slab":
            slab = plan.slabs[index]
            slab.section = value
            self.project.assignments["slab_sections"][slab.id] = value
        self.project.dirty = True
        self.refresh_all()

    def draw_plan(self) -> None:
        if not hasattr(self, "canvas"):
            return
        canvas = self.canvas
        canvas.delete("all")
        plan = self.project.plan
        if not plan.columns and not plan.grids:
            canvas.create_text(30, 30, anchor="nw", fill="#5b6a7d",
                               text="Configure pisos y grillas para generar la planta.")
            return
        xmin, ymin, xmax, ymax = plan.extent
        width = max(canvas.winfo_width(), 200) - 70
        height = max(canvas.winfo_height(), 200) - 60
        span_x = max(xmax - xmin, 1e-6)
        span_y = max(ymax - ymin, 1e-6)
        scale = min(width / span_x, height / span_y)
        ox = 40 + (width - span_x * scale) / 2
        oy = 30 + (height - span_y * scale) / 2

        def screen(x, y):
            return ox + (x - xmin) * scale, canvas.winfo_height() - oy - (y - ymin) * scale

        for slab in plan.slabs:
            points = [screen(x, y) for x, y in slab.coords]
            flat = [coordinate for point in points for coordinate in point]
            canvas.create_polygon(flat, fill="#fff9d9", outline="#d9c98a", width=1)
        for line in plan.grids:
            x1, y1 = screen(line.x1, line.y1)
            x2, y2 = screen(line.x2, line.y2)
            if line.kind in ("I1", "I2"):
                canvas.create_line(x1, y1, x2, y2, fill="#9c7bd6", width=2, dash=(6, 3))
            else:
                canvas.create_line(x1, y1, x2, y2, fill="#e1e6ee", width=1)
        for beam in plan.beams:
            point_a = next((c for c in plan.columns if c.id == beam.col_a), None)
            point_b = next((c for c in plan.columns if c.id == beam.col_b), None)
            if point_a and point_b:
                x1, y1 = screen(point_a.x, point_a.y)
                x2, y2 = screen(point_b.x, point_b.y)
                canvas.create_line(x1, y1, x2, y2, fill="#5d7285", width=2)
        for wall in plan.walls:
            point_a = next((c for c in plan.columns if c.id == wall.col_a), None)
            point_b = next((c for c in plan.columns if c.id == wall.col_b), None)
            if point_a and point_b:
                x1, y1 = screen(point_a.x, point_a.y)
                x2, y2 = screen(point_b.x, point_b.y)
                canvas.create_line(x1, y1, x2, y2, fill="#2e7d32", width=5)
        for column in plan.columns:
            px, py = screen(column.x, column.y)
            canvas.create_oval(px - 4, py - 4, px + 4, py + 4,
                               fill="#b23a2f", outline="white")
        for column in plan.columns:
            px, py = screen(column.x, column.y)
            canvas.create_text(px + 6, py - 6, text=column.id, anchor="sw",
                               font=("Segoe UI", 7), fill="#354357")
        for grid in plan.grids:
            if grid.kind in ("X", "Y"):
                x = grid.orig_x1 if grid.kind == "X" else grid.orig_x1
                y = grid.orig_y1 if grid.kind == "Y" else grid.orig_y1
                px, py = screen(x, y)
                canvas.create_text(px, py - 4, text=grid.id, anchor="s",
                                   font=("Segoe UI", 7, "bold"), fill="#7d8ca0")
            else:
                px, py = screen(grid.orig_x1, grid.orig_y1)
                canvas.create_text(px, py, text=grid.id, anchor="ne",
                                   font=("Segoe UI", 7, "bold"), fill="#7a5ab5")

    # -- validación -------------------------------------------------------
    def validate(self) -> None:
        issues = self.project.validate()
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity != "error"]
        if not issues:
            messagebox.showinfo("Validación", "Proyecto sin observaciones.")
        else:
            lines = []
            for issue in issues:
                label = "ERROR" if issue.severity == "error" else "AVISO"
                where = f" · {issue.area}" if issue.area else ""
                item = f" · {issue.item}" if issue.item else ""
                lines.append(f"{label}{where}{item}: {issue.message}")
            _dialog_text(self, f"Validación · {len(errors)} errores, {len(warnings)} avisos",
                         "\n".join(lines))
        self.status.set(f"Validación: {len(errors)} error(es), {len(warnings)} aviso(s).")

    # -- archivo ----------------------------------------------------------
    def _confirm_discard(self) -> bool:
        if not self.project.dirty:
            return True
        return messagebox.askyesno("Cambios sin guardar",
                                   "Hay cambios sin guardar. ¿Continuar de todos modos?")

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.project = Project.new()
        self.refresh_all()
        self.status.set("Proyecto nuevo creado con los datos de la plantilla 4.0.")

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="Abrir proyecto ETABS CIXTOP",
            filetypes=[("Proyecto CIXTOP", "*.json"), ("Todos", "*.*")])
        if not path:
            return
        try:
            self.project = Project.load(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Abrir proyecto", str(exc))
            return
        self.refresh_all()
        self.status.set(f"Proyecto abierto: {path}")

    def save_project(self) -> None:
        initial = self.project.path.name if self.project.path else "proyecto_cixtop.json"
        path = filedialog.asksaveasfilename(
            title="Guardar proyecto", defaultextension=".json", initialfile=initial,
            filetypes=[("Proyecto CIXTOP", "*.json"), ("Todos", "*.*")])
        if not path:
            return
        try:
            self.project.save(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Guardar proyecto", str(exc))
            return
        self.refresh_all()
        self.status.set(f"Proyecto guardado: {path}")

    def import_excel(self) -> None:
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="Importar libro ETABS CIXTOP",
            filetypes=[("Libro con macros", "*.xlsm"), ("Libro Excel", "*.xlsx"), ("Todos", "*.*")])
        if not path:
            return
        try:
            self.project = Project.import_workbook(path)
            self.project.path = None
            self.project.dirty = True
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Importar Excel", str(exc))
            return
        self.refresh_all()
        self.status.set("Datos importados desde Excel. Guarda el proyecto para conservarlos.")

    # -- ETABS ------------------------------------------------------------
    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def connect_etabs(self) -> None:
        try:
            self.bridge.connect(start_if_needed=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Conexión ETABS", str(exc))
            self.etabs_state.configure(text="Sin conexión")
            return
        self.etabs_state.configure(text="Conectado")
        self._log("Conectado a ETABS.")

    def initialize_etabs(self) -> None:
        if not messagebox.askyesno("Nuevo modelo",
                                   "Se iniciará ETABS y se creará un modelo vacío. ¿Continuar?"):
            return
        try:
            self.bridge.initialize_blank()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("ETABS", str(exc))
            return
        self.etabs_state.configure(text="Conectado · modelo nuevo")
        self._log("ETABS listo en unidades Ton, m, C.")

    def export_one(self, label: str, function) -> None:
        try:
            result = function(self.project)
        except Exception as exc:  # noqa: BLE001
            self._log(f"Error al exportar {label}: {exc}")
            messagebox.showerror("ETABS", str(exc))
            return
        if isinstance(result, dict):
            message = ", ".join(f"{key}: {value}" for key, value in result.items())
        else:
            message = str(result)
        self._log(f"{label}: {message}")
        self.status.set(f"{label} exportado.")
        for line in self.bridge.log[-5:]:
            self._log("  " + line)
        self.bridge.log.clear()

    def export_plan(self) -> None:
        if not messagebox.askyesno(
                "Dibujar planta",
                "Se crearán columnas, vigas, losas y muros en ETABS. ¿Continuar?"):
            return
        try:
            result = self.bridge.export_plan(self.project, self.clean_model.get())
        except Exception as exc:  # noqa: BLE001
            self._log(f"Error al dibujar la planta: {exc}")
            messagebox.showerror("ETABS", str(exc))
            return
        message = ", ".join(f"{key}: {value}" for key, value in result.items())
        self._log("Planta: " + message)
        self.status.set("Planta exportada.")
        messagebox.showinfo("ETABS", "Planta exportada:\n" + message)

    def export_all(self) -> None:
        steps = [
            ("materiales", self.bridge.export_materials),
            ("secciones", self.bridge.export_sections),
            ("áreas", self.bridge.export_area_sections),
            ("cargas", self.bridge.export_loads),
            ("grillas", self.bridge.export_grids),
            ("niveles", self.bridge.export_stories),
        ]
        for label, function in steps:
            try:
                result = function(self.project)
            except Exception as exc:  # noqa: BLE001
                self._log(f"Detenido en {label}: {exc}")
                messagebox.showerror("Exportar todo", f"Falló {label}: {exc}")
                return
            self._log(f"{label}: {result}")
        try:
            result = self.bridge.export_plan(self.project, self.clean_model.get())
        except Exception as exc:  # noqa: BLE001
            self._log(f"Falló la planta: {exc}")
            messagebox.showerror("Exportar todo", f"Falló la planta: {exc}")
            return
        self._log("planta: " + ", ".join(f"{k} {v}" for k, v in result.items()))
        self.status.set("Exportación completa.")


def _grid_id(axis: str, index: int) -> str:
    if axis == "Y":
        return str(index)
    result = ""
    n = index
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def main() -> None:
    EtabsApp().mainloop()


if __name__ == "__main__":
    main()
