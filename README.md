# ETABS CIXTOP · aplicación Python

Aplicación de escritorio que reproduce el flujo de cálculo de **ETABS-CIXTOP 4.0**
sin depender de Excel. El libro `.xlsm` se usa solo como fuente de datos y de
lógica: los valores por defecto ya están incorporados en el código.

El proyecto se guarda en JSON (`.json`) y se exporta a ETABS por COM.

## Inicio

En Windows, instala Python 3.10 o posterior y las dependencias:

```powershell
py -m pip install -r requirements.txt
py -m etabs_gui
```

La ventana abre con un proyecto nuevo generado desde la plantilla 4.0:
12 niveles, 3 grillas X, 5 grillas Y, una grilla inclinada I1, 20 columnas,
31 vigas, 15 losas y 20 filas de muro listas para asignar.

## Dónde se ingresan los datos

La ventana tiene siete pestañas. Todos los valores se editan con doble clic
sobre la celda (o `Enter`), y los cambios regeneran la planta y la validación.

1. **Proyecto y grillas**
   - Nombre y descripción.
   - Cantidad de niveles, altura típica y altura del primer nivel →
     **Generar niveles**. La tabla muestra altura y elevación acumulada.
   - Grillas X e Y: cantidad, separación y **Generar**; también **+ Añadir**.
   - Grillas inclinadas tipo 1 (X1 abajo → X2 arriba) y tipo 2
     (Y1 izquierda → Y2 derecha).
2. **Materiales**
   - Nombre, tipo (Concrete, Rebar, Tendon, Steel, Masonry), `fc`, `Fy`, `fm`,
     módulo `E`, peso específico y Poisson. `E` se recalcula al cambiar `fc` o `fm`.
3. **Secciones**
   - Cantidades por tipo → **Generar secciones**.
   - Nombre, material, elemento (Columna/Viga), geometría (Rectangular,
     Circular, Perfil_I, Tubo_Rectangular, Tubo_Circular, Tipo_T, Tipo_L),
     dimensiones en cm y factores de fisuración `f22`/`f33`.
     Área e inercia se calculan solas.
4. **Losas y muros**
   - Losas: material, tipo de modelado, `Slab type`, espesor y modificadores.
   - Muros: material, tipo de modelado, espesor, modificadores y qué columnas
     une cada muro (los muros se asignan en la pestaña **Planta**).
5. **Cargas**
   - **Patrones**: nombre, tipo, multiplicador de peso propio y descripción.
   - **Sismo E.030**: `Z`, `U`, `S`, `Tp`, `TL`, `R`, `T`, excentricidad y
     patrones sísmicos por dirección. Calcula `ZUCS/R` y `K` en vivo.
   - **Fuente de masa**: nombre, banderas de masa y factores por patrón.
   - **Combinaciones**: nombre, tipo (Linear Add/Envelope) y factores escritos
     como `CM:1.4, CV:1.7`.
6. **Planta**
   - **Regenerar planta** reconstruye columnas, vigas, losas y muros desde las
     grillas.
   - El selector muestra Columnas, Vigas X/Y, Vigas inclinadas T1/T2, Muros y
     Losas. En la tabla se cambia la sección de cada objeto y, en muros, las
     columnas de inicio y fin.
   - El lienzo dibuja la planta con grillas, vigas, muros, losas y columnas.
7. **ETABS**
   - **Conectar ETABS** o **Nuevo modelo ETABS**.
   - Exportaciones individuales: niveles, grillas, materiales, secciones,
     losas/muros, cargas y combos, y dibujo de la planta.
   - **Exportar todo el modelo** ejecuta la secuencia completa.

## Archivos y formato

- **Nuevo / Abrir… / Guardar…**: proyecto en JSON, sin macros ni fórmulas.
- **Importar Excel…**: lectura opcional y de una sola vía desde un `.xlsm`
  o `.xlsx` para recuperar datos de la plantilla 4.0. Después de importar,
  guarda el proyecto en JSON.
- **Validar**: revisa alturas, elevaciones, grillas duplicadas, secciones y
  materiales sin asignar, y objetos de planta faltantes.

## Módulos

| Archivo | Contenido |
| --- | --- |
| `template.py` | Valores por defecto de la plantilla 4.0, fórmulas de sismo y listas de opciones. |
| `plan.py` | Geometría: grillas, extensión inclinada de 1.5 m, vigas, recorrido de caras para losas y muros. |
| `model.py` | Modelo `Project`, guardado/carga JSON, validación e importación opcional de Excel. |
| `etabs.py` | Puente COM (`comtypes`) con ETABS: niveles, grillas, materiales, secciones, áreas, cargas, combos y planta. |
| `app.py` | Interfaz Tkinter con las siete pestañas. |

## Requisitos y alcance

La exportación necesita ETABS instalado, su API COM registrada y `comtypes`.
Se usa `comtypes` y no `pywin32` porque el `IDispatch` de ETABS 22 falla con
`pywin32` (error `E_NOINTERFACE` al pedir `SapModel`). Sin ETABS la aplicación
funciona completa: edita, valida, dibuja y guarda JSON.

Antes de dibujar en ETABS revisa que los nombres de materiales y secciones
coincidan con los exportados. La exportación de grillas inclinadas y del
coeficiente sísmico usa tablas de base de datos de ETABS; si la versión no las
expone, la aplicación cae en el sistema de grillas cartesianas y registra el
aviso en el panel de la pestaña 7.

Las líneas de grilla se escriben como líneas generales con extremos explícitos.
ETABS recorta las líneas cartesianas al rectángulo X/Y y no las prolonga hasta
las grillas inclinadas; con extremos explícitos las líneas numeradas llegan
hasta la grilla inclinada, igual que en el lienzo.
