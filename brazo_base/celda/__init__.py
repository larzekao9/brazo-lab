from pathlib import Path

from brazo_base.celda.archivos import cargar_celda, guardar_celda
from brazo_base.celda.modelo import Celda, Objeto, Superficie

CELDA_DEMO = Path(__file__).resolve().parent.parent / "datos" / "celda_demo" / "celda.json"


def celda_demo() -> Celda:
    """La celda de práctica que viene con la plataforma (la que usa el simulador por defecto)."""
    return cargar_celda(CELDA_DEMO)


__all__ = ["Celda", "Objeto", "Superficie", "cargar_celda", "guardar_celda", "celda_demo", "CELDA_DEMO"]
