"""Parámetros del simulador. Casi todo es una ESTIMACIÓN (se marca) que se corrige midiendo en el laboratorio."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParametrosFisicos:
    """La pinza simulada."""

    fuerza_total_min_n: float = 28.0
    fuerza_total_max_n: float = 80.0
    """Fuerza de agarre de la PGE-50-26 a 20 % y 100 % (ficha técnica, de memoria: confirmar)."""
    velocidad_dedos_max_mm_s: float = 40.0
    carrera_mm: float = 26.0
    umbral_contacto_n: float = 0.4
    latencia_estado_pinza_s: float = 0.15
    """El registro de agarre muestra el valor viejo este tiempo tras ordenar un movimiento (como el real)."""
    duracion_inicializacion_s: float = 2.0
    duracion_recalibracion_s: float = 4.0


@dataclass
class ParametrosRobot:
    """Velocidades del brazo simulado (ESTIMADOS)."""

    velocidad_lineal_max_mm_s: float = 1000.0
    velocidad_articular_max_grados_s: float = 180.0
    duracion_minima_s: float = 0.15
    puerto_modbus_pinza: int = 60000
    maestros_modbus_max: int = 5


@dataclass
class ParametrosSimulador:
    fisicos: ParametrosFisicos = field(default_factory=ParametrosFisicos)
    robot: ParametrosRobot = field(default_factory=ParametrosRobot)
