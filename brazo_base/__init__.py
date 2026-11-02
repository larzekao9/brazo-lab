"""brazo-base: plataforma abierta para aprender y programar el Dobot CR5AS (simulador primero, brazo real después)."""
from brazo_base.brazo import Brazo
from brazo_base.celda import Celda, cargar_celda, celda_demo
from brazo_base.errores import (
    CeldaInvalida,
    ErrorBrazo,
    ErrorDelControlador,
    HerramientaNoResponde,
    NoAgarro,
    NoHabilitado,
    RecorridoProhibido,
    SinConexion,
)

__all__ = ["Brazo", "Celda", "cargar_celda", "celda_demo", "ErrorBrazo", "SinConexion", "NoHabilitado", "RecorridoProhibido", "NoAgarro",
           "HerramientaNoResponde", "ErrorDelControlador", "CeldaInvalida"]
__version__ = "0.1.0"
