# ETABS CIXTOP · Documentación técnica para evaluación por agente de IA

Versión de la aplicación: **5.0** · Fecha del documento: **2026-11-07**
Raíz del proyecto: `C:\Users\Andre\Documents\ChatGPT\ETABS`

Este documento describe **qué es**, **cómo está construido** y **cómo funciona** el
proyecto, con detalle de cada pantalla, cada entrada, cada salida y cada regla de
cálculo. Está escrito para que un agente de IA pueda auditar el sistema sin abrir
el código primero.

---

## 1. Resumen

Aplicación de escritorio en **Python + Tkinter** que reproduce la funcionalidad de
la plantilla Excel `ETABS-CIXTOP 4.0.xlsm` **sin depender de Excel**. Permite:

1. Definir un proyecto estructural: niveles, grillas (cartesianas e inclinadas),
   materiales, secciones de barra, losas, muros, cargas, sismo y combinaciones.
2. Generar automáticamente la planta: columnas en cruces de grillas, vigas entre
   columnas consecutivas y losas como caras cerradas del diagrama de grillas.
3. Editar todo en tablas con edición directa en la celda.
4. Guardar y abrir el proyecto como **JSON**.
5. Exportar el modelo a **ETABS** por COM (comtypes): niveles, grillas,
   materiales, secciones, áreas, cargas, combinaciones y geometría 3D.

Fuente de verdad: `etabs_gui/template.py` (valores por defecto y fórmulas).
El libro Excel es solo una fuente opcional de importación de una vía
(`Project.import_workbook`).

### 1.1 Ficha técnica

| Tema | Valor |
|---|---|
| Lenguaje | Python 3.10+ (probado en 3.10 y 3.14) |
| Interfaz | Tkinter / ttk, 7 pestañas |
| Persistencia | JSON UTF-8, `format: etabs-cixtop-project` |
| Puente ETABS | `comtypes` (no pywin32), API ETABS 22.x |
| Unidades internas (Python) | m, cm, kgf/cm², t/m³ |
| Unidades en ETABS | Tonf, m, °C (`UNITS_TON_M = 12`) |
| Dependencias | `comtypes>=1.4`, `openpyxl>=3.1` (openpyxl solo para importar Excel) |
| Punto de entrada | `py -m etabs_gui` → `etabs_gui/app.py::main` |
| Estado por defecto | 12 niveles, 3×5 grillas, 1 grilla inclinada, 28 materiales, 9 secciones, 20 columnas, 31 vigas, 15 losas, 20 filas de muro |

---

## 2. Cómo ejecutar

```powershell
cd C:\Users\Andre\Documents\ChatGPT\ETABS
py -m pip install -r requirements.txt
py -m etabs_gui
```

- Para exportar: abrir ETABS antes, o usar **7 · ETABS → Nuevo modelo ETABS**.
- Para solo usar la app: no hace falta ETABS ni Excel.
- Verificación rápida sin interfaz:

```powershell
py -c "from etabs_gui.model import Project; p=Project.new(); print(p.plan.summary()); print(len(p.validate()))"
# 20 columnas · 31 vigas · 15 losas · 20 muros
# 0
```

Archivos de salida:

| Salida | Quién la produce | Formato |
|---|---|---|
| Proyecto | `Project.save` | JSON |
| Modelo ETABS | `EtabsBridge.export_*` | Modelo COM en memoria de ETABS |
| Validación | `Project.validate` | Lista de `Issue` en pantalla |
| Bitácora ETABS | `EtabsBridge.log` | Texto en la pestaña 7 |

---

## 3. Arquitectura

### 3.1 Capas

```
┌──────────────────────────────────────────────────────────────┐
│ app.py  ·  Tkinter: 7 pestañas, tablas, lienzo, vista sección │
└───────────────┬──────────────────────────────┬───────────────┘
                │ edita                        │ exporta
                ▼                              ▼
┌──────────────────────────────┐   ┌───────────────────────────┐
│ model.py · Project           │   │ etabs.py · EtabsBridge    │
│  datos + validación + JSON   │◄──│  COM / comtypes / tablas  │
└───────┬──────────────┬───────┘   └───────────────┬───────────┘
        │ usa          │ usa                       │ usa
        ▼              ▼                           ▼
┌───────────────┐ ┌──────────────┐          ┌──────────────┐
│ plan.py       │ │ template.py  │          │ ETABS 22.x   │
│ geometría     │ │ defaults y   │          │ SapModel     │
│ de planta     │ │ fórmulas     │          └──────────────┘
└───────────────┘ └──────────────┘
```

Dependencias reales:

- `app` → `model`, `plan` (indirecto), `template`, `etabs`
- `etabs` → `model`, `template`
- `model` → `plan`, `template`
- `plan` → solo biblioteca estándar
- `template` → solo biblioteca estándar
- `project.py` → no lo importa nadie (módulo legado, ver §14)

### 3.2 Archivos

| Archivo | Líneas | Responsabilidad |
|---|---:|---|
| `etabs_gui/app.py` | 1516 | Interfaz completa: `Table`, `SectionPreview`, `EtabsApp`, acciones y dibujo |
| `etabs_gui/etabs.py` | 660 | Puente COM: conexión, unidades, exportaciones |
| `etabs_gui/model.py` | 678 | `Project`: datos, generación, validación, JSON, importación Excel |
| `etabs_gui/plan.py` | 341 | Motor geométrico: grillas, columnas, vigas, caras/losas, muros |
| `etabs_gui/template.py` | 277 | Constantes, materiales, secciones, fórmulas, cargas |
| `etabs_gui/project.py` | 171 | Modelo legado tipo Excel en memoria (no usado) |
| `etabs_gui/__main__.py` | 2 | `from .app import main; main()` |
| `README.md` | 96 | Guía de uso |
| `requirements.txt` | 2 | Dependencias |

### 3.3 Flujo de datos

```
Entrada del usuario (tabla / campo / botón)
        │
        ▼
Project (listas de dicts)  ──►  refresh_section_properties()
        │                        │
        │ generate_plan()        │
        ▼                        ▼
plan.Plan (Column/Beam/Slab/Wall)   Table.set_rows / SectionPreview / Canvas
        │
        ├──► JSON (save)
        └──► EtabsBridge.export_* (COM)
```

Regla central: **la interfaz nunca guarda estado propio**. Toda edición escribe en
`Project` y luego llama a `refresh_all()`, que reconstruye tablas, vista de
sección, planta y resumen.

### 3.4 Decisiones de diseño relevantes

| Decisión | Motivo |
|---|---|
| `comtypes` en lugar de `pywin32` | pywin32 devuelve `E_NOINTERFACE` al pedir `SapModel` en ETABS 22 |
| Decimal regional en tablas ETABS | `DatabaseTables` interpreta números con el separador decimal de Windows |
| Con grillas inclinadas, todas las líneas son `General` con extremos | ETABS recorta las líneas cartesianas al rectángulo X/Y y no llegan a la inclinada |
| Sin inclinadas, filas `X (Cartesian)` / `Y (Cartesian)` | Más simples y editables en ETABS |
| Edición en la celda con `Entry` superpuesto | Tkinter no tiene edición nativa en `Treeview`; evita diálogos flotantes |
| Desplegables con `Combobox` superpuesto | Replica las listas del Excel |
| Vista de sección en `Canvas` | Verificación visual inmediata de geometría y dimensiones |
| JSON plano con `deepcopy` | Sin macros, portable, inspeccionable por un agente |
| Valores por defecto en Python | Elimina la dependencia del `.xlsm` |

---

## 4. Modelo de datos

### 4.1 Clase `Project`

`Project` es un contenedor de atributos simples (listas y diccionarios). No usa
ORM ni base de datos.

| Atributo | Tipo | Contenido |
|---|---|---|
| `name`, `description` | `str` | Identificación del proyecto |
| `stories` | `list[dict]` | `{name, height, elevation}` |
| `grid_x` | `list[dict]` | `{id, coord, spacing}` |
| `grid_y` | `list[dict]` | `{id, coord, spacing}` |
| `inclined_x` | `list[dict]` | `{id, start, end}` (tipo 1) |
| `inclined_y` | `list[dict]` | `{id, start, end}` (tipo 2) |
| `spacing_x`, `spacing_y` | `float` | Separación usada por “Generar grillas” |
| `materials` | `list[dict]` | Biblioteca de materiales |
| `section_counts` | `dict[str,int]` | Cantidad por grupo de sección |
| `frame_sections` | `list[dict]` | Secciones de viga/columna |
| `slabs`, `walls` | `list[dict]` | Secciones de área |
| `patterns` | `list[dict]` | Patrones de carga |
| `seismic` | `dict` | Parámetros E.030 + patrones sísmicos |
| `mass_source` | `dict` | Nombre, banderas y factores de masa |
| `combos` | `list[dict]` | Combinaciones de carga |
| `assignments` | `dict` | Asignaciones por objeto (secciones, muros) |
| `plan` | `plan.Plan` | Resultado geométrico (no se guarda en JSON) |
| `path` | `Path \| None` | Archivo de origen |
| `dirty` | `bool` | Cambios sin guardar |

### 4.2 Esquema JSON

```json
{
  "format": "etabs-cixtop-project",
  "version": "5.0",
  "project": {
    "name": "PROYECTO \"EL ROWI\"",
    "description": "Sistema de porticos de 10 pisos",
    "stories": [
      { "name": "Piso 1", "height": 3.0, "elevation": 3.0 },
      { "name": "Piso 2", "height": 2.8, "elevation": 5.8 }
    ],
    "grid_x": [
      { "id": "A", "coord": 0.0, "spacing": 4.0 },
      { "id": "B", "coord": 4.0, "spacing": 4.5 },
      { "id": "C", "coord": 8.5, "spacing": 0.0 }
    ],
    "grid_y": [
      { "id": "1", "coord": 0.0, "spacing": 2.7 }
    ],
    "inclined_x": [
      { "id": "I1", "start": 11.5, "end": 12.5 }
    ],
    "inclined_y": [],
    "materials": [
      {
        "name": "Concreto fc 280", "kind": "Concrete",
        "fc": 280.0, "fy": 0.0, "fm": 0.0,
        "E": 250998.0, "weight": 2.4, "poisson": 0.2
      }
    ],
    "section_counts": {
      "vs_conc": 1, "vp_conc": 1, "vb_conc": 1, "col_conc": 6,
      "vp_steel_i": 0, "vs_steel_i": 0, "vs_hss": 0,
      "col_steel_i": 0, "col_hss": 0
    },
    "frame_sections": [
      {
        "name": "COL_CONC_1", "material": "Concreto fc 180",
        "element": "Columna", "geometry": "Rectangular",
        "d": 40.0, "bf": 40.0, "tw": 0.0, "tf": 0.0,
        "f22": 0.7, "f33": 0.7,
        "area": 1600.0, "inertia": 213333.3333,
        "rebar_cover": 4.0
      }
    ],
    "slabs": [
      {
        "name": "Losa_1", "material": "Concreto fc 280",
        "model_type": "Shell-Thin", "slab_type": "Slab",
        "thickness": 20.0, "carpet": 0.0, "rib_top": 0.0,
        "rib_bottom": 0.0, "spacing_1": 0.0, "spacing_2": 0.0,
        "mods": [1, 1, 1, 1, 1, 1, 1]
      }
    ],
    "walls": [
      {
        "name": "Wall_1", "material": "Concreto fc 280",
        "model_type": "Shell-Thick", "thickness": 20.0,
        "mods": [1, 1, 1, 0.6, 0.6, 0.6, 1]
      }
    ],
    "patterns": [
      { "name": "CM", "type": "Dead", "self_weight": 1.0,
        "description": "Carga muerta: peso propio + acabados + tabiqueria" }
    ],
    "seismic": {
      "Z": 0.45, "U": 1.0, "S": 1.05, "Tp": 0.6, "TL": 2.0,
      "R": 7.0, "T": 0.5, "eccentricity": 0.05,
      "patterns": [
        { "name": "SX", "type": "Quake", "direction": "X",
          "lateral": "User Coefficient" }
      ]
    },
    "mass_source": {
      "name": "MsSrc1", "include_self": false,
      "include_added": false, "include_loads": true,
      "factors": [ { "pattern": "CM", "factor": 1.0 } ]
    },
    "combos": [
      { "name": "1.4CM+1.7CV", "type": "Linear Add",
        "factors": { "CM": 1.4, "CV": 1.7 }, "notes": "Gravitacional" }
    ],
    "assignments": {
      "column_sections": { "A-1": "COL_CONC_1" },
      "beam_sections": { "VX-001": "VP_CONC_1" },
      "slab_sections": { "Losa_1": "Losa_1" },
      "wall_defs": [
        { "id": "M-001", "a": "A-1", "b": "B-1", "section": "Wall_1" }
      ]
    }
  }
}
```

`plan`, `path` y `dirty` se excluyen al guardar (`Project.to_dict`).

### 4.3 Convenciones

- **Longitudes de grilla/nivel**: metros.
- **Dimensiones de sección**: centímetros (`d`, `bf`, `tw`, `tf`, `thickness`).
- **Área de sección**: cm²; **inercia**: cm⁴. Solo para pantalla y JSON.
- **Esfuerzos**: kgf/cm². **Peso específico**: t/m³.
- **Coordenadas de planta**: metros, origen en la grilla mínima. Eje Y hacia arriba.
- Nombres `VACIO` (mayúsculas) y vacío significan “no dibujar” en ETABS.

### 4.4 Identificadores

| Objeto | Regla | Ejemplo |
|---|---|---|
| Grilla X | Letras (A, B, …, Z, AA…) | `A`, `B`, `C` |
| Grilla Y | Números | `1`, `2`, `3` |
| Columna | `grilla_X-grilla_Y` | `B-3` |
| Viga X/Y | `VX-001`, `VY-001` | `VX-012` |
| Viga inclinada tipo 1/2 | `VI1-001`, `VI2-001` | `VI1-004` |
| Losa | Nombre de sección de losa o `L-###` | `Losa_1`, `L-004` |
| Muro | `M-###` desde la definición | `M-001` |
| Sección | `PREFIJO_n` | `COL_CONC_1` |

---

## 5. Cálculo de materiales y secciones (`template.py`)

### 5.1 Materiales

- Concreto: `E = ceil(15000 · √fc)` kgf/cm².
- Acero: `fy = ceil(fy_ksi · 1000 / 14.2233)` kgf/cm²; `E = 2 000 000`.
- Albañilería: `E = 500 · fm`.
- En la interfaz, `E` se recalcula al editar `fc` (concreto) o `fm` (albañilería).
  `fy` solo aplica a acero/rebar/tendón.

Biblioteca por defecto: 10 concretos (fc 140…500), 5 rebar, 6 aceros, 6
albañilerías = **28 materiales**.

### 5.2 Secciones de barra

`section_properties(geometry, d, bf, tw, tf) → (área cm², I33 cm⁴)`.

| Geometría | Área | I33 (eje fuerte) | Campos usados |
|---|---|---|---|
| `Rectangular` | `d·bf` | `bf·d³/12` | d, bf |
| `Circular` | `π·d²/4` | `π·d⁴/64` | d |
| `Tipo_T` | `bf·tf + (d−tf)·tw` | centroide + Steiner | d, bf, tw, tf |
| `Tipo_L` | `d·tw + (bf−tw)·tf` | centroide + Steiner | d, bf, tw, tf |
| `Perfil_I` | `2·bf·tf + (d−2tf)·tw` | `[tw(d−2tf)³ + 2(bf·tf³ + 12·bf·tf·((d−tf)/2)²)]/12` | d, bf, tw, tf |
| `Tubo_Rectangular` | `d·bf − (d−2tf)(bf−2tw)` | `[bf·d³ − (bf−2tw)(d−2tf)³]/12` | d, bf, tw, tf |
| `Tubo_Circular` | `π(d² − (d−2tw)²)/4` | `π(d⁴ − (d−2tw)⁴)/64` | d, tw |

Centroide para T:

```
A_ala = bf·tf          y_ala = tf/2
A_alma = (d−tf)·tw     y_alma = tf + (d−tf)/2
ȳ = (A_ala·y_ala + A_alma·y_alma) / A
I33 = Σ(I_local + A_i·y_i²) − A·ȳ²
```

Para L: pata vertical `d·tw` y pata horizontal `(bf−tw)·tf`; mismos pasos.

Casos límite: si `A ≤ 0`, devuelve `(0, 0)`. `bf < tw` y `d < tf` se recortan con
`max(..., 0)`; no generan valores negativos.

Valores de control:

| Sección | Área | I33 |
|---|---|---|
| T 40×20×1×1 | 59,00 cm² | 10 233,05 cm⁴ |
| L 40×40×1×1 | 79,00 cm² | 12 845,32 cm⁴ |
| Rect 40×40 | 1 600,00 cm² | 213 333,33 cm⁴ |

`refresh_section_properties()` recalcula **todas** las secciones al abrir,
refrescar o cambiar geometría. Corrige proyectos viejos con inercia 0.

### 5.3 Modificadores de fisuración

`section_modifiers(element) → (f22, f33)`:

| Elemento | f22 | f33 |
|---|---:|---:|
| Columna | 0.7 | 0.7 |
| Viga de Borde | 1.0 | 1.0 |
| Viga Principal / Secundaria | 1.0 | 0.35 |
| Vacío | 1.0 | 1.0 |

En ETABS se envían en el arreglo de 8 modificadores: índice 4 → `f22`,
índice 5 → `f33`.

### 5.4 Grupos de secciones por defecto

| Prefijo | Elemento | Geometría | d | bf | tw | tf | Cantidad |
|---|---|---|---:|---:|---:|---:|---:|
| VS_CONC | Viga Secundaria | Rectangular | 40 | 40 | 0 | 0 | 1 |
| VP_CONC | Viga Principal | Rectangular | 40 | 40 | 0 | 0 | 1 |
| VB_CONC | Viga de Borde | Rectangular | 20 | 20 | 0 | 0 | 1 |
| COL_CONC | Columna | Rectangular | 40 | 40 | 0 | 0 | 6 |
| VP_STEEL_I | Viga Principal | Perfil_I | 40 | 20 | 0.8 | 1.2 | 0 |
| VS_STEEL_I | Viga Secundaria | Perfil_I | 30 | 15 | 0.6 | 1.0 | 0 |
| VS_HSS | Viga Secundaria | Tubo_Rectangular | 40 | 40 | 1 | 1 | 0 |
| COL_STEEL_I | Columna | Perfil_I | 40 | 30 | 1 | 1.6 | 0 |
| COL_HSS | Columna | Tubo_Rectangular | 40 | 40 | 1 | 1 | 0 |

“Generar secciones” conserva por nombre las secciones existentes, recalcula
área/inercia, elimina asignaciones inválidas y regenera la planta.

### 5.5 Sismo E.030

```
C = 2.5                     si T ≤ Tp
C = 2.5·Tp/T                si Tp < T < TL
C = 2.5·Tp·TL/T²            si T ≥ TL
ZUCS/R = Z·U·C·S/R
K = 1                       si T ≤ 0.5 s
K = min(0.75 + 0.5·T, 2.0)  si T > 0.5 s
```

Se muestran en vivo y se aplican a ETABS en la tabla
`Load Pattern Definitions - Auto Seismic - User Coefficient`
(`IsAuto=Yes`, dirección X/Y, `EccRatio`, `C`, `K`).

### 5.6 Cargas por defecto

- Patrones: `CM` (Dead, 1.0), `CV` (Live, 0), `CVT` (RoofLive, 0).
- Sísmicos: `SX` (X), `SY` (Y), tipo Quake, `User Coefficient`.
- Sismo: Z 0.45, U 1.0, S 1.05, Tp 0.6, TL 2.0, R 7.0, T 0.5, e 0.05.
- Masa: `MsSrc1`, cargas especificadas activas; factores CM 1.0, CV 0.5, CVT 0.25.
- 10 combinaciones: 9 lineales + `ENVOLVENTE`.

---

## 6. Geometría de planta (`plan.py`)

### 6.1 Construcción de líneas

`build_grids(grid_x, grid_y, inclined_x, inclined_y)`:

1. Calcula el rectángulo cartesiano `[xmin,xmax]×[ymin,ymax]`.
2. Extiende cada grilla inclinada **1.5 m** por ambos extremos
   (`EXT_INCLINADA = 1.5`), con `extend_segment`.
3. Guarda dos juegos de coordenadas: **extendidas** (para dibujar e intersectar)
   y **originales** (`orig_*`, para etiquetas y extensión total).
4. Genera líneas `X`, `Y`, `I1` (tipo 1) e `I2` (tipo 2).

Tipo 1: `(x=start, y=ymin) → (x=end, y=ymax)`.
Tipo 2: `(x=xmin, y=start) → (x=xmax, y=end)`.

### 6.2 Columnas

`_columns_on(lines)` intersecta **todo par de líneas de distinto tipo**
(X–Y, X–I1, Y–I1, etc.). Cada intersección produce una columna con id
`X-Y` y posición real del cruce. Tolerancia `1e-7`.

Con los valores por defecto: 15 cruces X–Y + 5 cruces Y–I1 = **20 columnas**.

### 6.3 Vigas

`_beams_for(lines, columns)`:

1. Toma las columnas que pertenecen a la línea (`grid_a` o `grid_b` igual al id).
2. Las ordena por parámetro sobre la línea.
3. Crea una viga por cada par consecutivo.

Con los valores por defecto: 12 vigas X + 15 vigas Y + 4 vigas inclinadas =
**31 vigas**.

### 6.4 Losas

Algoritmo de caras planares (`_FaceWalker`):

1. Todos los vértices (extremos de línea y columnas) se unifican con
   redondeo a 4 decimales.
2. Cada segmento entre vértices consecutivos se agrega en ambos sentidos.
3. Se recorre cada arista sin usar tomando siempre el giro más a la izquierda
   (`next_left`).
4. Cada cara cerrada con ≥3 vértices y área > `0.01` m² se convierte en losa.
5. Se calculan área y centroide por fórmula de polígono.

Con los valores por defecto: **15 losas**.

### 6.5 Muros

Cada definición `{id, a, b, section}`:

- Si `a` y `b` existen como columnas: centro, longitud real.
- Si no: muro con longitud 0 (fila en edición).
- El id `M-###` es estable; `VACIO` o columnas vacías no se dibujan en ETABS.

### 6.6 Resumen y extensión

`Plan.summary()` → `"N columnas · N vigas · N losas · N muros"`.
`Plan.extent` = rectángulo que abarca líneas extendidas y originales.

Límites: recorrido de caras máximo 5 000 pasos por cara; área mínima 0.01 m²;
tolerancia geométrica 1e-7.

---

## 7. Validación (`Project.validate`)

Devuelve `list[Issue]` con `severity` (`error` / `warning`), `message`, `area`,
`item`. La interfaz muestra un diálogo con conteo y detalle.

### 7.1 Niveles

| Regla | Severidad |
|---|---|
| Sin niveles | error |
| Nivel sin nombre | error |
| Nombre repetido | error |
| Altura ≤ 0 | error |
| Elevación no creciente | error |

### 7.2 Grillas

| Regla | Severidad |
|---|---|
| Sin grillas en X o Y | error |
| Grilla sin ID | error |
| IDs repetidos | error |
| Coordenada no numérica | error |
| Coordenadas no crecientes | warning |
| Menos de 2 grillas por eje | warning |
| ID de inclinada repetido | error |
| Inclinada vertical/horizontal/nula | warning |

### 7.3 Materiales y secciones

| Regla | Severidad |
|---|---|
| Sección con material inexistente | error |
| Sección con `d ≤ 0` o `bf ≤ 0` | error |
| Nombres de sección repetidos | error |
| Sin secciones de losa / muro | error |
| Losa/muro con material inexistente | error |
| Espesor ≤ 0 | error |

### 7.4 Planta

| Regla | Severidad |
|---|---|
| Muro con columna A/B inexistente | warning |
| Muro con longitud nula | warning |
| Columna/viga con sección inexistente | warning |
| Losa/muro con sección inexistente | warning |

### 7.5 Cargas

| Regla | Severidad |
|---|---|
| Combinación sin nombre o repetida | error |
| Combinación usa patrón inexistente | error |
| Envolvente sin combinaciones lineales | warning |

Estado por defecto: **0 hallazgos**.

---

## 8. Persistencia e importación

### 8.1 Guardar / abrir

- `Project.save(path)`: escribe `{format, version, project}` con `indent=2`,
  UTF-8, sin BOM. Marca `dirty=False` y actualiza `path`.
- `Project.load(path)`: acepta el envoltorio o un JSON plano. Restaura atributos,
  rellena `assignments` con valores por defecto, regenera secciones y planta.
- `Project.from_dict`: ignora `plan`, `path`, `dirty`; si no hay niveles crea 1.
- Si `wall_defs` queda vacío, crea 20 filas `M-001…M-020`.

La planta **no** se guarda: siempre se reconstruye desde grillas y asignaciones.

### 8.2 Importar Excel (opcional, una vía)

`Project.import_workbook(path)`:

- Requiere `openpyxl` y la hoja `PROYECTO` (si no existe: `ValueError`).
- Abre con `data_only=False, keep_vba=True`.
- Mapeo de celdas:

| Dato | Rango / celda |
|---|---|
| Nombre / descripción | `K8`, `K9` |
| Cantidad, altura típica, primer nivel | `G13`, `G14`, `G15` |
| Coordenadas X | columnas `K` (id) y `M` (valor), filas 20–69 |
| Coordenadas Y | columnas `S` y `U`, filas 20–69 |
| Inclinadas tipo 1 | columnas `AB, AC, AD`, filas 20–69 |
| Inclinadas tipo 2 | columnas `AF, AG, AH`, filas 20–69 |
| Materiales | filas 76–108: `C, F, H, J, L, N, P, R` |
| Secciones | filas 122–198: `C, F, I, K, M, N, O, P, Q, R` |
| Losas | filas 211–213 |
| Muros | filas 220–229 |
| Patrones | filas 329–331, 348, 349 |
| Sismo | `I335`…`I341`, `I345` |
| Combinaciones | filas 360–369, casos en fila 359 |

- No sobrescribe con vacío: solo reemplaza listas si leyó al menos un elemento.
- No guarda macros ni fórmulas; convierte todo a datos del modelo.
- Después de importar, hay que guardar el JSON para conservar.

---

## 9. Puente ETABS (`etabs.py`)

### 9.1 Conexión

- `GetActiveObject("CSI.ETABS.API.ETABSObject")` para ETABS abierto.
- Si no hay: helper `ETABSv1.Helper` o `CSiAPIv1.Helper`.
- `start_if_needed=True` crea ETABS con `CreateObjectProgID` +
  `ApplicationStart`.
- `initialize_blank()`: `InitializeNewModel(12)` + `File.NewBlank()`.
- `self.model = application.SapModel`; si falla, error explícito.
- `_require()` impide exportar sin conexión.

### 9.2 Unidades y números

- `UNITS_TON_M = 12` (Tonf, m, °C) para geometría y cargas.
- `UNITS_KGF_CM = 14` solo durante materiales.
- `_num(valor)` formatea a 6 decimales, recorta ceros y usa el separador decimal
  del sistema (`GetLocaleInfoW(0x0400, 0x0E)`).
- `_ret(resultado)`: el código de retorno es el **último** entero de la tupla de
  comtypes.
- `_names(resultado)`: los nombres vienen en una sub-tupla intermedia.
- `_pick_name`: obtiene el nombre creado (`AddByPoint`, `AddCartesian`).

### 9.3 Tablas (`DatabaseTables`)

- Leer: `GetTableForEditingArray(key, "") → [version, fields, n, flat, ret]`.
- Escribir: `SetTableForEditingArray(key, 0, fields, n, flat)` y luego
  `ApplyEditedTables(True)`.
- `flat` es una lista plana por filas de `len(fields)`.
- Si falla: `CancelTableEditing()`.

### 9.4 Exportaciones

| Método | Entrada | Salida | Detalle |
|---|---|---|---|
| `export_stories` | `stories` | nº niveles | `Story.SetStories_2(0, n, nombres, alturas, …)` |
| `export_grids` | grillas + inclinadas | nº líneas | Sistema `G1`; ver §9.5 |
| `export_materials` | 28 materiales | nº materiales | `SetMaterial`, `SetMPIsotropic`, `SetWeightAndMass`, `SetOConcrete/ORebar/OTendon/OSteel` |
| `export_sections` | secciones de barra | nº secciones | `SetRectangle/SetCircle/SetISection/SetTube/SetPipe/SetTee/SetAngle`; refuerzo si el material contiene “concreto”; modificadores |
| `export_area_sections` | losas + muros | nº áreas | `PropArea.SetSlab/SetWall` + `SetModifiers` |
| `export_loads` | patrones, sismo, combos | `{patterns, combinations}` | `LoadPatterns.Add`, `RespCombo.Add/SetCaseList`, tabla de sismo |
| `export_plan` | `project.plan` + niveles | `{columns, beams, slabs, walls}` | Puntos, barras y áreas por nivel |

### 9.5 Grillas en ETABS

- Se asegura la fila `G1` en `Grid Definitions - General`.
- Se conservan filas de otros sistemas; se reemplazan las de `G1`.
- **Con inclinadas**: todas las líneas se escriben como `General` con `X1,Y1,X2,Y2`
  explícitos. Las X abarcan `ymin_ext…ymax_ext`; las Y abarcan `xmin_ext…xmax_ext`;
  las inclinadas usan su segmento extendido.
- **Sin inclinadas**: filas `X (Cartesian)` y `Y (Cartesian)` con `Ordinate`.
- `BubbleLoc`: `End` para X, `Start` para Y e inclinadas (evita solapamiento).
  `BubbleLoc="None"` no se usa: ETABS descarta filas.
- `Visible=Yes`.
- Si `DatabaseTables` no está disponible: crea solo el origen `G1` y registra
  el aviso.

### 9.6 Planta en ETABS

- Requiere al menos una columna; si no, error.
- `SetModelIsLocked(False)`, unidades Ton-m, exporta niveles.
- Limpieza opcional (`clean_first`): borra todas las barras y áreas existentes.
- Puntos: `PointObj.AddCartesian(x, y, z, "", "", "Global", False, 0)`
  con caché por coordenada redondeada a 6 decimales.
- Base de cada columna: restricción de 6 grados de libertad en `z=0`.
- Columnas: `FrameObj.AddByPoint(base, nivel, "", sección, "COL_{id}")`,
  tramo por tramo entre elevaciones consecutivas.
- Vigas: por cada nivel, entre columnas `col_a` y `col_b`.
- Losas: `AreaObj.AddByPoint(n, puntos, "", sección, id)` por nivel.
- Muros: área de 4 puntos desde la elevación anterior hasta la actual.
- Se omiten secciones vacías o `VACIO`.
- Resultado: diccionario con conteos; la app lo muestra en el diálogo y la bitácora.

### 9.7 Limitaciones conocidas del puente

- **Fuente de masa**: este API no expone `SourceMass`; `_apply_mass_source` solo
  registra una nota. Se configura en ETABS (Define → Mass Source).
- Los nombres de sección y material deben existir antes de dibujar la planta.
- El refuerzo solo se asigna a materiales cuyo nombre contiene “concreto”.
- No hay transacción: si un paso falla, lo ya exportado permanece.
- Depende del orden: materiales → secciones → áreas → cargas → grillas → niveles
  → planta.

---

## 10. Interfaz: elementos comunes (`app.py`)

### 10.1 Ventana principal

- Título: `ETABS CIXTOP 5.0 · Proyecto estructural`.
- Tamaño inicial 1360×860, mínimo 1100×700, centrada en pantalla.
- Cabecera: nombre de la app, ruta del archivo y botones
  **Nuevo**, **Abrir…**, **Guardar…**, **Importar Excel…**, **Validar**.
- Barra de estado inferior: resumen de planta o mensaje de la última acción.
- Atajos: `Ctrl+N`, `Ctrl+O`, `Ctrl+S`.

### 10.2 Tabla reutilizable (`Table`)

- `Treeview` con encabezados, barras de desplazamiento y altura configurable.
- Edición **en la celda**:
  - Seleccionar y escribir inicia el editor con ese carácter.
  - Doble clic o `Enter` abre el editor.
  - `Tab` confirma y pasa a la celda editable siguiente; `Shift+Tab` retrocede.
  - `Escape` cancela; clic fuera confirma.
  - Numéricos aceptan coma o punto decimal; valor vacío = 0.
- Columnas con `options` abren un `Combobox` de solo lectura sobre la celda.
- Columnas `readonly` no se editan (área, inercia, elevación, IDs de planta).
- `set_rows` reemplaza las filas y conserva el formato con `fmt`.

### 10.3 Vista de sección (`SectionPreview`)

- `Canvas` lateral en la pestaña **3 · Secciones**.
- Dibuja a escala: Rectangular, Circular, Perfil_I, Tubo_Rectangular,
  Tubo_Circular, Tipo_T y Tipo_L.
- Muestra: nombre, geometría, elemento, cota `d` y `bf`, área, `I33`, `f22`,
  `f33`, y `d·bf·tw·tf`.
- Color azul para concretos, gris para acero.
- Si faltan dimensiones, muestra en rojo cuáles faltan.
- Se actualiza al seleccionar fila y al editar cualquier valor. La selección se
  conserva tras refrescar.

---

## 11. Interfaz: pestaña por pestaña

### 11.1 Pestaña 1 · Proyecto y grillas

**Entradas**

- Nombre y descripción (se guardan al escribir).
- Niveles: cantidad (1–50), altura típica (m), primer nivel (m),
  botón **Generar niveles**.
- Grillas X e Y: cantidad (2–50), separación (m), **Generar**, **+ Añadir**.
- Grillas inclinadas tipo 1 y tipo 2: **+ Añadir**, **Eliminar**.

**Tablas**

| Tabla | Columnas | Editable |
|---|---|---|
| Niveles | Story ID, altura, elevación | nombre y altura; elevación calculada |
| Grillas X/Y | Grid ID, coord, separación | id y coord; separación calculada |
| Inclinadas | ID, inicio, fin | todo |

**Comportamiento**

- Generar niveles: `Piso 1` con altura inicial y el resto con la típica;
  elevación acumulada.
- Editar una altura recalcula todas las elevaciones.
- Generar grillas: ids alfabéticos en X y numéricos en Y; coordenada acumulada
  por separación.
- Añadir grilla: busca el primer id libre y usa la última separación.
- Cualquier cambio reconstruye la planta (columnas, vigas, losas, muros).

**Salidas**: `stories`, `grid_x`, `grid_y`, `inclined_x`, `inclined_y`, y la
planta regenerada.

### 11.2 Pestaña 2 · Materiales

**Tabla**: nombre, tipo (Concrete/Rebar/Tendon/Steel/Masonry), `fc`, `Fy`, `fm`,
`E`, peso (t/m³), Poisson.

**Botones**: **+ Material**, **Eliminar**.

**Reglas**

- Cambiar `fc` recalcula `E` en concretos; `fm` en albañilería.
- No se puede eliminar un material usado por secciones, losas o muros.
- Renombrar un material actualiza todas las referencias (secciones, losas,
  muros) y rechaza nombres vacíos o repetidos (sin distinguir mayúsculas).

**Salida**: `materials` y las referencias actualizadas.

### 11.3 Pestaña 3 · Secciones

**Controles**

- Contadores por grupo (9 grupos, 0–50) y **Generar secciones**.
- **Eliminar seleccionada**.

**Tabla**

| Columna | Editable |
|---|---|
| Nombre | sí (renombra y propaga) |
| Material | desplegable con materiales |
| Elemento | desplegable: Columna, Viga Principal, Viga Secundaria, Viga de Borde |
| Geometría | desplegable con 7 geometrías |
| d, bf, tw, tf | numéricos (cm) |
| f22, f33 | numéricos |
| Área, I33 | solo lectura, recalculados |

**Comportamiento**

- Al cambiar elemento se recalculan `f22/f33`.
- Al cambiar cualquier dimensión se recalculan área e inercia de todas las
  secciones.
- Renombrar actualiza asignaciones de columnas y vigas; informa cuántas.
- El panel derecho dibuja la sección seleccionada (ver §10.3).

**Salida**: `frame_sections`, `assignments`, planta.

### 11.4 Pestaña 4 · Losas y muros

Dos sub-pestañas.

**Losas**

| Columna | Contenido |
|---|---|
| Nombre | id de la sección de losa |
| Material | desplegable |
| Modeling | Shell-Thin, Shell-Thick, Membrane, Layered |
| Slab type | Slab, Drop, Stiff, Ribbed, Waffle, Mat, Footing |
| e cm | espesor |
| f11, f22, f12, m11, m22, m12, v13/v23 | modificadores |

**Muros**: nombre, material, modeling, espesor y los mismos 7 modificadores.
Botones **+ Losa** / **+ Muro**.

**Salida**: `slabs`, `walls`, planta (las losas se asignan en la pestaña 6).

### 11.5 Pestaña 5 · Cargas

Cuatro sub-pestañas.

**Patrones**: nombre, tipo (Dead, SuperDead, Live, ReduceLive, Quake, Wind,
Snow, RoofLive, Other), peso propio, descripción. Botones **+ Patrón**,
**Eliminar**, **Restaurar plantilla**.

**Sismo E.030**: campos Z, U, S, Tp, TL, R, T, excentricidad; etiqueta en vivo
`ZUCS/R` y `K`; tabla de patrones sísmicos (nombre, dirección X/Y, carga lateral);
botón **Actualizar coeficiente**.

**Fuente de masa**: nombre, banderas (Element Self Mass, Additional Mass,
Specified Loads), tabla patrón/factor; **+ Fila**, **Eliminar**.

**Combinaciones**: nombre, tipo (Linear Add, Envelope), factores como texto
`CM:1.4, CV:1.7`, notas; **+ Combinación**, **Eliminar**.

**Salida**: `patterns`, `seismic`, `mass_source`, `combos`.

### 11.6 Pestaña 6 · Planta

**Controles**

- **Regenerar planta**.
- Selector **Ver**: Columnas, Vigas X, Vigas Y, Vigas inclinadas T1,
  Vigas inclinadas T2, Muros, Losas.
- Resumen de conteos.

**Lienzo**

| Elemento | Color / estilo |
|---|---|
| Losas | relleno crema `#fff9d9`, borde `#d9c98a` |
| Grillas X/Y | gris claro `#e1e6ee` |
| Grillas inclinadas | violeta discontinuo `#9c7bd6` |
| Vigas | gris azulado `#5d7285`, grosor 2 |
| Muros | verde `#2e7d32`, grosor 5 |
| Columnas | rojo `#b23a2f`, círculo |
| Etiquetas | id de columna y de grilla |

Escala automática al tamaño del lienzo; ejes en metros.

**Tabla por vista**

| Vista | Columnas editables |
|---|---|
| Columnas | ID, tipo, X, Y (lectura) · sección (desplegable), giro |
| Vigas X/Y/T1/T2 | ID, grilla, col A/B, centro (lectura) · sección |
| Muros | ID, longitud (lectura) · columna A/B, sección |
| Losas | ID, vértices, centro (lectura) · sección |

Editar una sección actualiza `assignments` y la tabla; editar un muro regenera
la planta.

**Salida**: `assignments` y `plan`, dibujo y conteos.

### 11.7 Pestaña 7 · ETABS

**Controles**

- **Conectar ETABS** (usa instancia abierta).
- **Nuevo modelo ETABS** (inicia ETABS y crea modelo vacío).
- Casilla **Borrar barras y áreas antes de dibujar**.
- Estado de conexión.

**Botones de exportación**

`Niveles`, `Grillas`, `Materiales`, `Secciones`, `Losas y muros`,
`Cargas y combos`, `Dibujar planta`, `Exportar todo el modelo`.

**Bitácora**: texto de solo lectura con el resultado de cada paso y los avisos
del puente (máximo 500 entradas en memoria).

**Secuencia completa** (`Exportar todo el modelo`):
materiales → secciones → áreas → cargas → grillas → niveles → planta.

**Salida**: modelo ETABS modificado + bitácora + diálogo de conteos.

---

## 12. Flujos de trabajo

### 12.1 Crear un proyecto desde cero

1. **Nuevo** (carga valores de la plantilla 4.0).
2. Pestaña 1: generar niveles y grillas; añadir inclinadas si aplica.
3. Pestaña 2: revisar o añadir materiales.
4. Pestaña 3: definir cantidades y geometrías; verificar la vista de sección.
5. Pestaña 4: definir losas y muros.
6. Pestaña 5: revisar patrones, sismo, masa y combinaciones.
7. Pestaña 6: regenerar planta y asignar secciones por objeto.
8. **Validar** hasta 0 errores.
9. **Guardar…**.

### 12.2 Exportar a ETABS

1. Abrir ETABS o **Nuevo modelo ETABS**.
2. **Conectar ETABS**.
3. Opcional: activar limpieza.
4. **Exportar todo el modelo**.
5. Revisar la bitácora y los conteos.
6. En ETABS: revisar grillas, secciones y vista 3D.

### 12.3 Migrar desde Excel

1. **Importar Excel…** y elegir el `.xlsm`.
2. Revisar los datos importados (no se copia todo: solo los rangos de §8.2).
3. **Guardar…** como JSON. Desde ese momento Excel no se vuelve a usar.

---

## 13. Pruebas y cifras verificadas

### 13.1 Modelo por defecto

| Verificación | Resultado |
|---|---|
| Niveles | 12 (`Piso 1`…`Piso 12`) |
| Grillas | 3 X (A, B, C) + 5 Y (1…5) + 1 inclinada (I1) |
| Materiales | 28 |
| Secciones de barra | 9 |
| Secciones de área | 2 |
| Columnas | 20 |
| Vigas | 31 |
| Losas | 15 |
| Muros (filas) | 20, sin columnas asignadas |
| Validación | 0 hallazgos |

### 13.2 Exportación real (ETABS 22.5.1)

| Objeto | Cantidad |
|---|---|
| Niveles | 12 |
| Líneas de grilla | 9 (3 X, 5 Y, 1 inclinada) |
| Materiales | 28 |
| Secciones de barra | 9 |
| Secciones de área | 2 |
| Patrones | 5 (3 gravitacionales + 2 sísmicos) |
| Combinaciones | 10 |
| Columnas dibujadas | 240 (20 × 12) |
| Vigas dibujadas | 372 (31 × 12) |
| Losas dibujadas | 180 (15 × 12) |
| Muros dibujados | 0 (filas sin columnas) |

### 13.3 Pruebas de sección

- T 40×20×1×1 → 59,00 cm² / 10 233,05 cm⁴.
- L 40×40×1×1 → 79,00 cm² / 12 845,32 cm⁴.
- Rectangular 40×40 → 1 600,00 cm² / 213 333,33 cm⁴.
- Cambio de geometría recalcula área e inercia y actualiza la vista.
- Renombrar `COL_CONC_1` → `COL_RENOMBRADA` actualiza 20 columnas; sin
  referencias al nombre viejo; validación 0.
- Renombrar un material actualiza 9 referencias en el modelo por defecto.

### 13.4 Pruebas de interfaz

- Escribir sobre una celda abre el editor en el sitio (sin diálogo).
- `Enter` confirma; `Tab` confirma y avanza; `Escape` cancela.
- Desplegables abren y aplican el valor elegido.
- Vista de sección: 12–17 elementos de canvas por geometría; aviso cuando faltan
  `tw`/`tf`.
- Captura verificada de la pestaña 3 con T 40×20×1×1.

---

## 14. Limitaciones y riesgos conocidos

1. **Muros por defecto vacíos**: 20 filas `M-001…M-020` sin columnas A/B.
   Se exportan 0 muros hasta asignarlos en la pestaña 6.
2. **Fuente de masa no exportada**: el API no expone `SourceMass`; solo se
   registra una nota.
3. **Inercia débil (I22) no calculada en Python**: solo se muestra I33; ETABS
   calcula ambas al crear la sección.
4. **Sin deshacer/rehacer**: cada edición es definitiva en memoria hasta
   cerrar sin guardar.
5. **Sin pegado múltiple ni edición por rango** en tablas.
6. **La planta no se persiste**: se reconstruye; si cambian grillas, cambian ids
   y las asignaciones pueden quedar huérfanas (la validación avisa).
7. **Nombres sensibles en ETABS**: materiales y secciones deben existir antes de
   dibujar; el orden de exportación importa.
8. **Cero rollback en ETABS**: un fallo a mitad deja objetos ya creados.
9. **Dependencia de la configuración regional** para tablas de ETABS
   (separador decimal).
10. **`project.py` es legado** y no se usa: contiene stubs con `print` y datos
    simulados. No debe evaluarse como funcionalidad activa.
11. **Automatización de la interfaz de ETABS no fiable** para verificación
    visual: las capturas se hacen por BitBlt de la ventana.
12. **Unidades**: la app asume que el usuario ingresa cm para secciones y m para
    grillas/niveles; no hay conversión automática si se cambia de unidad en ETABS.
13. **Validación de duplicados** de secciones compara nombres exactos; ETABS
    puede tratarlos sin distinguir mayúsculas.
14. **Slabs/Walls**: 7 modificadores en la app se expanden a 10 en ETABS;
    el séptimo se duplica en los índices 6 y 7.

---

## 15. Puntos de extensión

| Necesidad | Dónde cambiar |
|---|---|
| Nueva geometría de sección | `template.section_properties`, `GEOMETRY_OPTIONS`, rama en `EtabsBridge.export_sections`, polígono en `SectionPreview.redraw` |
| Nueva pestaña | `EtabsApp._build`, `_build_*_tab`, `refresh_all` |
| Nuevo paso de exportación | `EtabsBridge.export_*`, botón en `_build_etabs_tab`, secuencia en `export_all` |
| Nuevo campo del proyecto | atributo en `Project.__init__`, `to_dict/from_dict` (automático), UI y validación |
| Nueva regla de validación | `Project.validate` |
| Otro formato de persistencia | `Project.save/load` |
| Importar más celdas de Excel | `Project.import_workbook` |

Convención: toda edición de UI debe terminar en `refresh_all()`; todo cálculo
derivado debe vivir en `template` o `model`, no en la interfaz.

---

## 16. Glosario

| Término | Significado |
|---|---|
| **Nivel / story** | Piso estructural con altura y elevación |
| **Grilla** | Línea de referencia; cartesiana (X/Y) o inclinada (I1/I2) |
| **Grilla tipo 1 (I1)** | Inclinada que va de un X a otro entre el Y mínimo y máximo |
| **Grilla tipo 2 (I2)** | Inclinada que va de un Y a otro entre el X mínimo y máximo |
| **Columna** | Intersección de dos grillas de distinto tipo |
| **Viga** | Tramo entre columnas consecutivas sobre una grilla |
| **Losa** | Cara cerrada del diagrama de grillas |
| **Muro** | Área vertical entre dos columnas y dos niveles |
| **Sección de barra** | Perfil de viga/columna (`frame_section`) |
| **Sección de área** | Perfil de losa o muro (`slab`, `wall`) |
| **Modificador** | Factor de rigidez (`f11`, `f22`, `f33`, …) |
| **f22 / f33** | Factores de fisuración para inercia débil/fuerte |
| **Patrón** | Caso de carga (Dead, Live, Quake…) |
| **Combinación** | Suma ponderada de patrones |
| **Envolvente** | Combinación que toma el máximo de otras combinaciones |
| **VACIO** | Sección centinela: no dibujar el objeto |

---

## 17. Checklist de evaluación para el agente

### 17.1 Verificación estática

- [ ] `python -m py_compile etabs_gui/*.py` sin errores.
- [ ] `Project.new().validate()` devuelve 0.
- [ ] `Project.new().plan.summary()` = `20 columnas · 31 vigas · 15 losas · 20 muros`.
- [ ] `len(Project.new().materials)` = 28; `len(frame_sections)` = 9.
- [ ] `section_properties("Tipo_T", 40, 20, 1, 1)` = `(59.0, 10233.05…)`.
- [ ] `section_properties("Tipo_L", 40, 40, 1, 1)` = `(79.0, 12845.32…)`.
- [ ] Guardar y cargar un JSON reproduce el mismo resumen y validación.
- [ ] `rename_section` actualiza `assignments` y no deja referencias viejas.

### 17.2 Verificación de interfaz

- [ ] Abre sin excepciones y muestra las 7 pestañas.
- [ ] Editar una celda no abre diálogo; `Enter`/`Tab`/`Escape` funcionan.
- [ ] Los desplegables aparecen en: tipo de material, material, elemento,
  geometría, modeling, slab type, tipo de patrón, dirección sísmica, patrón de
  masa, tipo de combinación, sección de planta y columnas de muro.
- [ ] La vista de sección cambia al seleccionar filas y al editar dimensiones.
- [ ] El lienzo de planta dibuja grillas, vigas, losas, muros y columnas con la
  leyenda de colores de §11.6.

### 17.3 Verificación ETABS (si hay ETABS disponible)

- [ ] Conectar y exportar materiales: 28.
- [ ] Exportar grillas: 9 líneas; las X/Y llegan a la inclinada I1.
- [ ] Exportar secciones: 9; T y L aparecen como `Tee` y `Angle`.
- [ ] Exportar cargas: 5 patrones y 10 combinaciones.
- [ ] Dibujar planta: 240 columnas, 372 vigas, 180 losas, 0 muros.
- [ ] Cambiar una sección y reexportar: ETABS refleja la nueva geometría.

### 17.4 Criterios de aceptación

- El proyecto funciona sin Excel y sin macros.
- Los cálculos de sección coinciden con las fórmulas de §5.2.
- La planta es geométricamente consistente: toda viga une dos columnas
  existentes; toda losa tiene ≥3 vértices y área > 0.01 m².
- Guardar/cargar no pierde datos ni cambia conteos.
- Exportar dos veces no duplica niveles, materiales ni secciones.
- La validación detecta material faltante, dimensión no positiva, grilla
  duplicada y combinación con patrón inexistente.

---

## 18. Etiqueta de desarrollo · `predimensionamiento-estructural-automatico`

### 18.1 Integración

La pestaña 9 (`StructuralDesignTab`) recibe la instancia del analizador
arquitectónico y el proyecto activo. Reutiliza los dibujos DXF cargados, la
clasificación de capas y el número de niveles del proyecto. La geometría DXF
se convierte a metros según la unidad seleccionada por el usuario.

### 18.2 Los tres desarrollos incorporados

- **Propuesta geométrica:** `structural_design.py` genera nodos candidatos
  desde extremos e intersecciones de capas clasificadas como muro o columna.
  Conecta candidatos alineados dentro de la luz máxima indicada. Los paños
  rectangulares requieren candidatos en sus cuatro esquinas y vigas candidatas
  en los cuatro lados.
- **Predimensionamiento:** propone secciones guía de vigas con relaciones
  geométricas iniciales y una referencia de sección cuadrada de columna basada
  en cargas uniformes, número de pisos y un área tributaria supuesta. Para
  losas, usa la relación entre lados como orientación preliminar.
- **Alternativas:** presenta tres subconjuntos de nodos priorizados por
  puntuación geométrica. La vista distingue los nodos seleccionados. Los
  criterios y advertencias se conservan en el resultado del motor.

### 18.3 Restricciones de ingeniería

Los puntos son candidatos, no columnas aprobadas. Los muros DXF pueden ser
tabiquería; la clasificación de capa no acredita su condición portante. Los
muros bajos/parapetos se excluyen de la generación de apoyos. La detección de
losas se limita a celdas rectangulares con cuatro lados apoyados por vigas
candidatas; no resuelve paños irregulares, huecos ni condiciones reales de
borde. Las secciones no son verificaciones de resistencia ni de servicio.

El módulo no ejecuta análisis estructural, no dimensiona placas del sistema
dual, no verifica E.030/E.060/E.070, derivas, torsión, flexocompresión,
esbeltez, cortante, confinamiento, cimentaciones ni refuerzo. Los valores de
carga y el área tributaria usados para la referencia de columna son hipótesis
editables, no resultados de un modelo de cargas. La alternativa con menos
elementos no se debe interpretar como óptima sin análisis.

No existe transferencia automática a `Project.plan` ni exportación directa a
ETABS en esta versión. La separación es intencional: evita alterar las grillas
y el modelo existente sin revisión del usuario. Una integración posterior debe
convertir las propuestas aprobadas a entidades editables del modelo y conservar
la trazabilidad entre DXF, nivel y elemento estructural.

### 18.4 Archivos

- `etabs_gui/structural_design.py`: motor geométrico, estimaciones y alternativas.
- `etabs_gui/structural_design_tab.py`: interfaz de la pestaña 9.
- `tests/test_structural_design.py`: pruebas unitarias del motor.

## Anexo A · Árbol del repositorio

```
ETABS/
├── README.md
├── DOCUMENTACION_TECNICA.md   ← este archivo
├── requirements.txt
├── .gitignore
└── etabs_gui/
    ├── __init__.py
    ├── __main__.py
    ├── app.py
    ├── etabs.py
    ├── model.py
    ├── plan.py
    ├── project.py            (legado, no usado)
    └── template.py
```

## Anexo B · Salida gráfica del grafo de conocimiento

Si existe `graphify-out/`, contiene un grafo del proyecto generado con graphify
(no forma parte del programa):

- `graph.html`: visualización interactiva.
- `graph.json`: nodos/aristas con comunidades.
- `GRAPH_REPORT.md`: auditoría, nodos centrales y preguntas sugeridas.
- `cost.json`, `manifest.json`: costo y control de incrementalidad.

El grafo corresponde a este mismo código; sirve para navegar relaciones entre
módulos, no para ejecutar la aplicación.
