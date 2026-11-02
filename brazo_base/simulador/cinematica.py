"""Cinemática ESQUEMÁTICA del brazo: dos eslabones en un plano vertical, herramienta siempre vertical, giro de la muñeca libre.

No es el CR5 real: usa sus medidas principales (hombro a 147 mm, eslabones de 427 y 357 mm) pero ignora los desfases laterales de la
muñeca y deja la pinza apuntando hacia abajo (`rx = -180`, `ry = 0`), que es como la usa `EjecutorReal`. Sirve para tres cosas: decidir
si una pose está fuera de alcance, dar `GetAngle()` coherente con `GetPose()` y dibujar un brazo esquemático. `GetAngle` y
`MovJ(joint=...)` son consistentes entre sí dentro del simulador, pero los ángulos de un brazo real no dan la misma pose acá.
"""
from __future__ import annotations

import math

ALTURA_HOMBRO_MM = 147.0
ESLABON_1_MM = 427.0
ESLABON_2_MM = 357.0
MUNECA_A_BRIDA_MM = 150.0
RADIO_MINIMO_MM = 120.0
MARGEN_ALCANCE_MM = 5.0
Pose = tuple[float, float, float, float, float, float]


def _normalizar_grados(valor: float) -> float:
    return (valor + 180.0) % 360.0 - 180.0


def angulos_para_pose(x: float, y: float, z: float, rz: float) -> tuple[float, ...] | None:
    """Los 6 ángulos (grados) con la brida en `(x, y, z)` mirando hacia abajo y girada `rz`, o `None` si está fuera de alcance."""
    radio = math.hypot(x, y)
    if radio < RADIO_MINIMO_MM:
        return None
    dz = z + MUNECA_A_BRIDA_MM - ALTURA_HOMBRO_MM
    distancia = math.hypot(radio, dz)
    if not abs(ESLABON_1_MM - ESLABON_2_MM) + MARGEN_ALCANCE_MM <= distancia <= ESLABON_1_MM + ESLABON_2_MM - MARGEN_ALCANCE_MM:
        return None
    angulo_hombro = math.atan2(dz, radio) + math.acos(
        (ESLABON_1_MM**2 + distancia**2 - ESLABON_2_MM**2) / (2 * ESLABON_1_MM * distancia)
    )
    interior_codo = math.acos((ESLABON_1_MM**2 + ESLABON_2_MM**2 - distancia**2) / (2 * ESLABON_1_MM * ESLABON_2_MM))
    flexion_codo = -(math.pi - interior_codo)
    antebrazo_absoluto = angulo_hombro + flexion_codo
    q1 = math.degrees(math.atan2(y, x))
    return (
        q1,
        math.degrees(angulo_hombro),
        math.degrees(flexion_codo),
        -90.0 - math.degrees(antebrazo_absoluto),
        90.0,
        _normalizar_grados(rz - q1),
    )


def pose_para_angulos(angulos: tuple[float, ...]) -> Pose:
    """Pose `(x, y, z, rx, ry, rz)` de la brida para 6 ángulos; la herramienta se informa siempre vertical."""
    puntos = puntos_del_brazo(angulos)
    x, y, z = puntos[-1]
    return (x, y, z, -180.0, 0.0, _normalizar_grados(angulos[0] + angulos[5]))


def puntos_del_brazo(angulos: tuple[float, ...]) -> list[tuple[float, float, float]]:
    """Base, hombro, codo, muñeca y brida, en mm, para dibujar el brazo."""
    q1, q2, q3, q4 = (math.radians(a) for a in angulos[:4])
    antebrazo = q2 + q3
    herramienta = antebrazo + q4
    radios = [0.0, 0.0, ESLABON_1_MM * math.cos(q2)]
    alturas = [0.0, ALTURA_HOMBRO_MM, ALTURA_HOMBRO_MM + ESLABON_1_MM * math.sin(q2)]
    radios.append(radios[2] + ESLABON_2_MM * math.cos(antebrazo))
    alturas.append(alturas[2] + ESLABON_2_MM * math.sin(antebrazo))
    radios.append(radios[3] + MUNECA_A_BRIDA_MM * math.cos(herramienta))
    alturas.append(alturas[3] + MUNECA_A_BRIDA_MM * math.sin(herramienta))
    return [(r * math.cos(q1), r * math.sin(q1), z) for r, z in zip(radios, alturas)]


def esta_al_alcance(x: float, y: float, z: float) -> bool:
    """Si la brida puede estar en `(x, y, z)` con la herramienta vertical."""
    return angulos_para_pose(x, y, z, 0.0) is not None
