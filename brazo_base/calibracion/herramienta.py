"""Asistentes para medir el largo (TCP) de una herramienta.

1. `largo_por_apoyo`: con la herramienta VERTICAL, se apoya la punta en una superficie cuya altura se conoce y se lee la z de la brida: el largo es la diferencia. No necesita
   la orientación. Es lo más simple y lo que hizo el ajedrez a mano (`z_tope`).
2. `calibrar_por_pivote`: se toca el MISMO punto fijo con la punta desde 3 o más orientaciones distintas y se resuelve el vector brida→punta por mínimos cuadrados. Necesita
   la convención de Euler de las poses (`R = Rz·Ry·Rx`), que hay que comprobar con `herramientas/verificar_geometria.py` antes de fiarse del resultado.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from brazo_base.errores import CeldaInvalida
from brazo_base.simulador.cinematica import rotacion_de_euler

LARGO_MAXIMO_MM = 600.0


def largo_por_apoyo(z_brida_mm: float, z_superficie_mm: float) -> float:
    """Largo de la herramienta vertical: `z` de la brida con la punta apoyada menos la `z` de la superficie (ambas en el sistema de la base)."""
    largo = float(z_brida_mm) - float(z_superficie_mm)
    if not 0 < largo <= LARGO_MAXIMO_MM:
        raise CeldaInvalida(f"El largo da {largo:.1f} mm: tiene que estar entre 0 y {LARGO_MAXIMO_MM:.0f} mm. Revisá que la punta esté apoyada y la altura de la superficie")
    return largo


def calibrar_por_pivote(poses: Sequence[Sequence[float]]) -> dict:
    """Vector brida→punta `(tx, ty, tz)` en el sistema de la brida, el punto fijo `(x, y, z)` y el residuo (RMS, mm), a partir de poses `(x, y, z, rx, ry, rz)` de la brida con la punta en el mismo punto.

    Raises:
        CeldaInvalida: con menos de 3 poses, o si las orientaciones son casi iguales (la solución no queda determinada).
    """
    if len(poses) < 3 or any(len(p) != 6 for p in poses):
        raise CeldaInvalida("Hacen falta al menos 3 poses completas (x, y, z, rx, ry, rz) tocando el mismo punto")
    filas, derecha = [], []
    for p in poses:
        R = rotacion_de_euler(*p[3:])
        filas.append(np.hstack([R, -np.eye(3)]))  # p + R·t = c  →  R·t − c = −p
        derecha.append(-np.array(p[:3], dtype=float))
    A, b = np.vstack(filas), np.concatenate(derecha)
    if np.linalg.matrix_rank(A, tol=1e-6 * max(1.0, np.abs(A).max())) < 6 or np.linalg.cond(A) > 1e4:
        raise CeldaInvalida("Las orientaciones son demasiado parecidas: tocá el punto inclinando la herramienta de formas bien distintas (30° o más)")
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    residuo = float(np.sqrt(np.mean((A @ x - b) ** 2)))
    t, c = x[:3], x[3:]
    return {"vector_mm": [float(v) for v in t], "largo_mm": float(np.linalg.norm(t)), "punto_fijo_mm": [float(v) for v in c], "residuo_mm": residuo}
