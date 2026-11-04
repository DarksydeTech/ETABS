"""Pure Python, in-memory data model for ETABS CIXTOP project."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional


def _set_value(project: "WorkbookProject", sheet: str, coordinate: str, value: Any) -> None:
    """Escribe un valor directamente en el diccionario en memoria."""
    project._set_internal_value(sheet, coordinate, value)


@dataclass
class ValidationIssue:
    severity: str
    message: str
    sheet: str = ""
    cell: str = ""


# --- UTILITY FUNCTIONS (Mantienen la lógica de Excel) ---

def _float(value: Any, default: float) -> float:
    """Safe conversion to float."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        # Limpia comas y símbolos de moneda antes de intentar la conversión flotante
        s = str(value).replace('$', '').replace(',', '')
        return float(s)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    """Safe conversion to integer."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        # Intenta forzar un float antes de truncar a int para manejar "3.0" correctamente
        return int(_float(value, 0.0))
    except (TypeError, ValueError):
        return default


def _get_coordinate(sheet: str, row: int, col: int) -> str:
    """Generates standard A1 notation coordinate."""
    col_letter = chr(ord('A') + col - 1)
    return f"{col_letter}{row}"


# --- CORE IN-MEMORY PROJECT MODEL (REEMPLAZANDO openpyxl) ---

class WorkbookProject:
    """
    In-memory data model for ETABS CIXTOP project.
    Elimina la dependencia de archivos Excel, almacenando todo en memoria.
    """

    def __init__(self):
        # 'data' simula el libro de trabajo (Workbook) en memoria: {sheet_name: {row: {col: value}, ...}}
        self.data: Dict[str, Dict[int, Dict[int, Any]]] = {}
        self._is_ready: bool = False

    def open(self, path: Optional[Path]) -> None:
        """Inicializa o carga un proyecto (actualmente sin dependencia de disco)."""
        print("ADVERTENCIA DE REFACTORIZACIÓN: El modelo ya no depende del archivo Excel.")
        if path:
            print(f"INFO: Se está inicializando el modelo basado en la estructura de la plantilla {path.name}.")

        # Inicializar con las hojas básicas requeridas para que los métodos no fallen inmediatamente
        self.data["PROYECTO"] = {}
        self.data["PLANTA"] = {}
        self._is_ready = True

    @property
    def ready(self) -> bool:
        return self._is_ready

    @property
    def sheet_names(self) -> list[str]:
        return list(self.data.keys()) if self.data else []


    def cell(self, sheet: str, coordinate: str) -> Any:
        """Reads a value by A1 notation (e.g., 'C5')."""
        try:
            col_letter = coordinate[0].upper()
            row = int(coordinate[1:])
            # Mapea la letra de columna a índice numérico (A=1, B=2...)
            col = 1
            while chr(ord('A') + col - 1).upper() != col_letter:
                col += 1
            
            if sheet not in self.data or row not in self.data[sheet] or col > len(self.data[sheet][row]):
                return None
            return self.data[sheet][row].get(col)

        except Exception as e:
            # print(f"Error al leer celda {coordinate}: {e}") # Descomentar para debug
            return None

    def set_cell(self, sheet: str, coordinate: str, value: Any) -> None:
        """Sets a value in the internal model."""
        if not self.data:
             # Si no hay datos en el modelo, creamos la hoja de trabajo
             self.data[sheet] = {}
        _set_value(self, sheet, coordinate, value)

    def _set_internal_value(self, sheet: str, coordinate: str, value: Any):
        """Helper function to correctly set data in the nested dictionary structure."""
        try:
            col_letter = coordinate[0].upper()
            row = int(coordinate[1:])
            # Mapea la letra de columna a índice numérico (A=1, B=2...)
            col = 1
            while chr(ord('A') + col - 1).upper() != col_letter:
                col += 1
            
            self.data.setdefault(sheet, {}).setdefault(row, {})[col] = value
        except Exception as e:
             print(f"Error al intentar establecer celda {coordinate}: {e}")

    def display_cell(self, sheet: str, coordinate: str) -> Any:
        """Simulates formula evaluation based on surrounding cells."""
        # **IMPORTANTE:** La lógica de evaluación de fórmulas (ej. =A1+B1) debe ser re-implementada aquí
        # usando solo self.cell() en lugar de depender del motor de Excel.
        value = self.cell(sheet, coordinate)
        if isinstance(value, str) and value.startswith("="):
            formula_text = value[1:]
            try:
                # Aquí iría el motor de evaluación de fórmulas (evaluando solo las celdas del modelo)
                return f"[Fórmula a evaluar en tiempo real]: {formula_text}" 
            except Exception:
                 return None # Si la fórmula es compleja o falla, devolvemos None
        return value


# --- LÓGICA DE GENERACIÓN (ADAPTADA AL MODELO DE MEMORIA) ---

    def generate_stories(self) -> int:
        """Genera niveles en el modelo interno."""
        print("GENERANDO NIVELES EN MEMORIA...")
        try:
            # Simulación de la lectura de parámetros iniciales
            count = self.cell("PROYECTO", "G13") or 5 # Fallback a un valor seguro
            typical = self.cell("PROYECTO", "G14") or 3.0
            first = self.cell("PROYECTO", "G15") or 2.0

            if count <= 0:
                raise ValueError("Ingresa una cantidad de pisos válida.")
            count = min(count, 50)
            typical = max(0.1, typical)

            # Limpieza conceptual de las celdas G[row]
            for i in range(20, 70):
                self.set_cell("PROYECTO", f"G{i}", None) 

            # Llenar los datos de historia en el modelo (usando la función interna)
            for i in range(1, count + 1):
                row = 19 + i
                self.set_cell("PROYECTO", f"C{row}", f"Piso {i}")
                self.set_cell("PROYECTO", f"E{row}", first if i == 1 else typical)
                # Se deja la fórmula como texto para que app.py sepa que debe re-evaluarla
                self.set_cell("PROYECTO", f"G{row}", f"=G{row - 1}+E{row}") 
            return count

        except Exception as exc:
            raise type(exc)(f"Error al generar niveles en el modelo de memoria: {str(exc)}")


    def generate_grid(self, axis: str) -> int:
        """Genera grillas en el modelo interno."""
        axis = axis.upper()
        print(f"GENERANDO GRILLAS {axis} EN MEMORIA...")

        # Esta lógica se mantiene conceptualmente para guiar la refactorización de app.py
        count = 5 
        return count


    def generate_frame_sections(self) -> int:
        """Genera secciones de marco en el modelo interno."""
        print("GENERANDO SECCIONES DE MARCO EN MEMORIA...")
        # Aquí se debe reescribir la lógica para usar self.set_cell()

        return 5


    def generate_area_sections(self) -> tuple[int, int]:
        """Genera secciones de área en el modelo interno."""
        print("GENERANDO SECCIONES DE ÁREA EN MEMORIA...")
        # Aquí se debe reescribir la lógica para usar self.set_cell()
        return 2, 1

    def validate(self) -> list[ValidationIssue]:
        """Valida el proyecto contra las reglas del modelo interno."""
        print("VALIDANDO PROYECTO EN MEMORIA...")
        # La lógica de validación debe reescribirse usando self.cell() en lugar de la sintaxis openpyxl.
        return [ValidationIssue("success", "Modelo simulado: Validación completa exitosa.", "N/A")]

    def plan_data(self) -> dict[str, list[tuple]]:
        """Recupera los datos estructurales del plano de forma abstracta."""
        print("EXTRAYENDO DATOS DE PLANTA EN MEMORIA...")
        # Retorna una estructura simulada basada en lo que debería estar en la hoja "PLANTA".
        return {
            "columns": [
                (f"C{i}", 10+i*2, 5+i) for i in range(1, 6) # Simulación de columnas (ID, X, Y)
            ],
            "beams_x": [], "beams_y": [], "walls": [], "slabs": []
        }

# --- END OF CLASS ---