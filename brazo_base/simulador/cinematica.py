"""Cinemática del CR5 con las medidas del URDF del proyecto (la misma geometría que usa el validador de seguridad).

Antes el simulador usaba un modelo esquemático de dos eslabones y sus ángulos no servían para dibujar el brazo real. Ahora la cinemática
directa es la del URDF y la inversa es numérica (mínimos cuadrados amortiguados con partida en los ángulos actuales, para seguir una misma
solución del brazo). Las poses son las de la BRIDA, `(x, y, z, rx, ry, rz)` en mm y grados, con la convención `R = Rz(rz) · Ry(ry) · Rx(rx)`.

Lo que NO está comprobado contra el brazo real: que el URDF y los ángulos del controlador coincidan (`control_brazo.verificar_geometria` del
ajedrez compara las dos lecturas en el laboratorio; ver sección 9 del plan) ni que la convención de Euler sea la de DobotStudio.
"""
from __future__ import annotations

import math

import numpy as np

from brazo_base.seguridad import geometria

Pose = tuple[float, float, float, float, float, float]
TOLERANCIA_POSICION_MM = 0.05
TOLERANCIA_ROTACION_RAD = 5e-4
ITERACIONES_MAXIMAS = 120
AMORTIGUACION = 1e-3
PASO_NUMERICO_RAD = 1e-5
LIMITES = np.radians(np.array(geometria.LIMITES_ARTICULACIONES, dtype=float))
ORIGENES = [np.array(o) * 1000.0 for o, _ in geometria.JUNTAS]
EJES = [e for _, e in geometria.JUNTAS]


def _normalizar_grados(valor: float) -> float:
    return (valor + 180.0) % 360.0 - 180.0


def _rotacion(eje, radianes: float) -> np.ndarray:
    x, y, z = eje
    c, s = math.cos(radianes), math.sin(radianes)
    t = 1 - c
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y], [t * x * y + s * z, t * y * y + c, t * y * z - s * x], [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def rotacion_de_euler(rx: float, ry: float, rz: float) -> np.ndarray:
    """`Rz(rz) · Ry(ry) · Rx(rx)` con los ángulos en grados."""
    return _rotacion((0, 0, 1), math.radians(rz)) @ _rotacion((0, 1, 0), math.radians(ry)) @ _rotacion((1, 0, 0), math.radians(rx))


def euler_de_rotacion(R: np.ndarray) -> tuple[float, float, float]:
    """Inversa de `rotacion_de_euler`, en grados."""
    ry = math.asin(max(-1.0, min(1.0, -R[2, 0])))
    if abs(R[2, 0]) < 0.999999:
        rx, rz = math.atan2(R[2, 1], R[2, 2]), math.atan2(R[1, 0], R[0, 0])
    else:  # cardán bloqueado: se reparte todo en rz
        rx, rz = 0.0, math.atan2(-R[0, 1], R[1, 1])
    return math.degrees(rx), math.degrees(ry), math.degrees(rz)


def fk(angulos_grados) -> tuple[np.ndarray, np.ndarray]:
    """Rotación y posición (mm) de la brida (el origen de J6) para 6 ángulos en grados."""
    R, p = np.eye(3), np.zeros(3)
    for origen, eje, g in zip(ORIGENES, EJES, angulos_grados):
        p = p + R @ origen
        R = R @ _rotacion(eje, math.radians(g))
    return R, p


def pose_para_angulos(angulos: tuple[float, ...]) -> Pose:
    """Pose `(x, y, z, rx, ry, rz)` de la brida para 6 ángulos."""
    R, p = fk(angulos)
    return (float(p[0]), float(p[1]), float(p[2]), *euler_de_rotacion(R))


def pose_vertical(x: float, y: float, z: float, rz: float) -> Pose:
    """Pose de la brida con la herramienta mirando hacia abajo (`rx = 180`, `ry = 0`)."""
    return (x, y, z, 180.0, 0.0, rz)


def _error(R_objetivo: np.ndarray, p_objetivo: np.ndarray, R: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Error de 6 componentes: posición en mm y rotación como vector eje-ángulo en el sistema del mundo (rad, escalado a mm por 100)."""
    delta = R_objetivo @ R.T
    cos = max(-1.0, min(1.0, (np.trace(delta) - 1) / 2))
    angulo = math.acos(cos)
    if angulo < 1e-9:
        rot = np.zeros(3)
    elif math.pi - angulo < 1e-6:
        eje = np.sqrt(np.maximum((np.diag(delta) + 1) / 2, 0))
        rot = eje * angulo
    else:
        rot = angulo / (2 * math.sin(angulo)) * np.array([delta[2, 1] - delta[1, 2], delta[0, 2] - delta[2, 0], delta[1, 0] - delta[0, 1]])
    return np.concatenate([p_objetivo - p, rot * 100.0])


SEMILLAS = [(-90, 40, -100, 60, 90, 0), (90, 40, -100, 60, 90, 0), (0, 40, -100, 60, 90, 0), (-90, 70, -60, -10, 90, 0), (-150, 90, -110, 150, 50, 0), (-125, 90, -75, 160, 55, 0), (298.5, 35.3, -150.7, 27.4, 90.4, -38.8)]
"""Posturas de partida para la cinemática inversa cuando la actual no converge (es un método local)."""


def _resolver_desde(R_obj: np.ndarray, p_obj: np.ndarray, inicio) -> tuple[float, ...] | None:
    q = np.radians(np.array(inicio, dtype=float))
    for _ in range(ITERACIONES_MAXIMAS):
        R, p = fk(np.degrees(q))
        e = _error(R_obj, p_obj, R, p)
        if np.linalg.norm(e[:3]) < TOLERANCIA_POSICION_MM and np.linalg.norm(e[3:]) / 100.0 < TOLERANCIA_ROTACION_RAD:
            return tuple(float(v) for v in np.degrees(q))
        J = np.empty((6, 6))
        for i in range(6):
            dq = q.copy()
            dq[i] += PASO_NUMERICO_RAD
            R2, p2 = fk(np.degrees(dq))
            J[:, i] = (_error(R_obj, p_obj, R2, p2) - e) / -PASO_NUMERICO_RAD
        paso = np.linalg.solve(J.T @ J + AMORTIGUACION * np.eye(6), J.T @ e)
        mayor = np.max(np.abs(paso))
        if mayor > 0.3:
            paso *= 0.3 / mayor
        q = np.clip(q + paso, LIMITES[:, 0], LIMITES[:, 1])
    return None


def _equivalente_cercano(q: tuple[float, ...], referencia: tuple[float, ...]) -> tuple[float, ...]:
    """Suma vueltas completas (360°) a cada articulación para quedar lo más cerca de `referencia` sin salir de su rango: así el movimiento no da una vuelta de más."""
    salida = []
    for i, (v, ref) in enumerate(zip(q, referencia)):
        lo, hi = math.degrees(LIMITES[i][0]), math.degrees(LIMITES[i][1])
        mejor = v
        for k in (-2, -1, 1, 2):
            candidato = v + 360.0 * k
            if lo <= candidato <= hi and abs(candidato - ref) < abs(mejor - ref):
                mejor = candidato
        salida.append(mejor)
    return tuple(salida)


def angulos_para_pose_completa(pose: Pose, semilla: tuple[float, ...] | None = None, alternativas: bool = True) -> tuple[float, ...] | None:
    """Ángulos (grados) que ponen la brida en `pose`, o `None` si no hay solución dentro de los límites de articulación.

    Parte de `semilla` (los ángulos actuales) para seguir la misma solución del brazo. Con `alternativas` y si no converge, prueba otras posturas de partida y se queda
    con la solución más cercana a `semilla` (un `MovL` pasa `alternativas=False` en cada punto de la recta: no puede saltar de una solución a otra).
    """
    R_obj, p_obj = rotacion_de_euler(*pose[3:]), np.array(pose[:3], dtype=float)
    if semilla is not None:
        q = _resolver_desde(R_obj, p_obj, semilla)
        if q is not None or not alternativas:
            return None if q is None else _equivalente_cercano(q, semilla)
    soluciones = [q for q in (_resolver_desde(R_obj, p_obj, inicio) for inicio in SEMILLAS) if q is not None]
    if not soluciones:
        return None
    if semilla is None:
        return soluciones[0]
    return min((_equivalente_cercano(q, semilla) for q in soluciones), key=lambda q: sum(abs(a - b) for a, b in zip(q, semilla)))


def angulos_para_pose(x: float, y: float, z: float, rz: float, semilla: tuple[float, ...] | None = None) -> tuple[float, ...] | None:
    """Los 6 ángulos con la brida en `(x, y, z)` mirando hacia abajo y girada `rz`, o `None` si está fuera de alcance."""
    return angulos_para_pose_completa(pose_vertical(x, y, z, rz), semilla)


def puntos_del_brazo(angulos: tuple[float, ...]) -> list[tuple[float, float, float]]:
    """Base y origen de J1 a J6, en mm, para dibujar el brazo."""
    R, p = np.eye(3), np.zeros(3)
    puntos = [tuple(p)]
    for origen, eje, g in zip(ORIGENES, EJES, angulos):
        p = p + R @ origen
        R = R @ _rotacion(eje, math.radians(g))
        puntos.append(tuple(float(v) for v in p))
    return puntos


def esta_al_alcance(x: float, y: float, z: float) -> bool:
    return angulos_para_pose(x, y, z, 0.0) is not None
