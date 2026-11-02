"""Geometría del Dobot CR5AS para validar poses y trayectorias en ángulos de articulación (sin mover nada).

El movimiento por ángulos (`MovJ(joint=...)`) no pasa por el piso de `z_tope` que sí respetan las poses cartesianas, así que acá se comprueba,
con la cinemática directa del URDF del proyecto, que una pose (y el camino en línea recta en el espacio de articulaciones hasta ella):
  1. respeta los límites de cada articulación,
  2. no mete el codo, la muñeca ni la pinza dentro de la mesa (el plano donde está atornillada la base),
  3. no deja la punta de los dedos por debajo del tablero, y
  4. no hace chocar entre sí dos partes del brazo que no son vecinas.

Las medidas (`JUNTAS`) salen de `assets/dobot_cr5as/dobot_cr5as.urdf` y un test las compara con ese archivo. Lo que NO se puede comprobar sin el
brazo real es que los ángulos del controlador signifiquen lo mismo que los del URDF: `control_brazo.verificar_geometria` compara las dos lecturas.
Todas las distancias están en metros.
"""
from __future__ import annotations

import numpy as np

JUNTAS = (
    ((0.0, 0.0, 0.147), (0.0, 0.0, 1.0)),
    ((0.0, 0.122, 0.0), (0.0, 1.0, 0.0)),
    ((0.0, -0.116, 0.427), (0.0, 1.0, 0.0)),
    ((0.0, 0.116, 0.357), (0.0, 1.0, 0.0)),
    ((0.0, 0.0, 0.116), (0.0, 0.0, 1.0)),
    ((0.0, 0.0, 0.105), (0.0, 1.0, 0.0)),
)
"""Origen de cada articulación respecto de la anterior y su eje (J1 a J6)."""
CUERPO_PINZA_Z = 0.02
PUNTA_URDF_Z = 0.02 + 0.157
"""Distancia de la brida a la punta de los dedos en el modelo URDF (con los dedos de fábrica)."""
LARGO_PINZA_DEFECTO = 0.217
"""Distancia de la brida a la punta de los dedos que se usa si no se midió otra (`ParametrosAgarre.largo_pinza_mm`): el modelo más 40 mm de dedos largos."""
LARGO_CUERPO_PINZA = 0.117
"""Desde la brida hasta donde empiezan los dedos (el cuerpo de la pinza)."""

LIMITES_ARTICULACIONES = ((-360, 360), (-180, 180), (-160, 160), (-360, 360), (-360, 360), (-360, 360))
"""Rango permitido de J1 a J6, en grados. Los del brazo real (URDF y hoja de datos) son ±360° salvo J3, que es ±160°; J2 se limita a ±180° a
propósito: más allá el brazo atraviesa la base y la mesa, y eso ya lo comprueba la geometría."""

MARGEN_MESA = 0.06
"""Cuánto por encima del plano de la base tienen que quedar el codo, la muñeca y el cuerpo de la pinza (radio de los eslabones)."""
PUNTA_MINIMA_SIN_TABLERO = 0.03
"""Altura mínima de la punta de los dedos si todavía no se midió la altura del tablero (`z_tope`)."""
TOLERANCIA_TABLERO = 0.003
DISTANCIA_MINIMA_ENTRE_ESLABONES = 0.10
"""Distancia mínima entre los ejes de dos eslabones no vecinos (la suma de sus radios más un poco de aire)."""
GRADOS_POR_MUESTRA = 5

NOMBRES_ESLABONES = ("la columna de la base", "el hombro", "el brazo", "el antebrazo", "la primera muñeca", "la segunda muñeca", "la pinza")


def _rotacion(eje: tuple[float, float, float], grados: float) -> np.ndarray:
    a = np.radians(grados)
    x, y, z = eje
    c, s = np.cos(a), np.sin(a)
    t = 1 - c
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y], [t * x * y + s * z, t * y * y + c, t * y * z - s * x], [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def puntos_del_brazo(angulos: list[float] | tuple[float, ...], largo_pinza: float = LARGO_PINZA_DEFECTO) -> dict:
    """Posiciones del brazo para unos ángulos (J1 a J6, grados): `articulaciones` (la base y el origen de J1 a J6), `cuerpo_pinza`, `punta` y `eslabones`
    (los 7 segmentos que se usan para detectar choques)."""
    rotacion = np.eye(3)
    punto = np.zeros(3)
    articulaciones = [punto.copy()]
    for (origen, eje), grados in zip(JUNTAS, angulos):
        punto = punto + rotacion @ np.array(origen)
        rotacion = rotacion @ _rotacion(eje, grados)
        articulaciones.append(punto.copy())
    cuerpo = punto + rotacion @ np.array([0.0, 0.0, CUERPO_PINZA_Z])
    punta = punto + rotacion @ np.array([0.0, 0.0, largo_pinza])
    eslabones = [(articulaciones[i], articulaciones[i + 1]) for i in range(6)] + [(articulaciones[6], punta)]
    return {"articulaciones": articulaciones, "cuerpo_pinza": cuerpo, "punta": punta, "eslabones": eslabones}


def _distancia_entre_segmentos(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> float:
    u, v, w = b - a, d - c, a - c
    uu, uv, vv, uw, vw = u @ u, u @ v, v @ v, u @ w, v @ w
    denominador = uu * vv - uv * uv
    s = 0.0 if denominador < 1e-12 else float(np.clip((uv * vw - vv * uw) / denominador, 0, 1))
    t = float(np.clip((uv * s + vw) / vv, 0, 1)) if vv > 1e-12 else 0.0
    s = float(np.clip((uv * t - uw) / uu, 0, 1)) if uu > 1e-12 else 0.0
    return float(np.linalg.norm((a + u * s) - (c + v * t)))


def punta_minima_para(z_tope_mm: float | None, largo_pinza: float = LARGO_PINZA_DEFECTO) -> float:
    """Altura mínima de la punta de los dedos (m) sobre el plano de la base, a partir de `z_tope` (mm, lo que lee `GetPose()` con las puntas apoyadas en
    el tablero y la herramienta 0, o sea la brida): el tablero queda `largo_pinza` más abajo. Sin `z_tope`, `PUNTA_MINIMA_SIN_TABLERO`."""
    if z_tope_mm is None:
        return PUNTA_MINIMA_SIN_TABLERO
    return z_tope_mm / 1000 - largo_pinza - TOLERANCIA_TABLERO


def problemas_de_pose(angulos: list[float] | tuple[float, ...], z_tope_mm: float | None = None, largo_pinza: float = LARGO_PINZA_DEFECTO) -> list[str]:
    """Por qué una pose no se puede usar (lista vacía si es válida): límites de articulación, mesa, tablero y choques entre eslabones."""
    problemas: list[str] = []
    if len(angulos) != 6:
        return ["Hacen falta los 6 ángulos J1 a J6"]
    for i, (valor, (minimo, maximo)) in enumerate(zip(angulos, LIMITES_ARTICULACIONES), start=1):
        if not minimo <= valor <= maximo:
            problemas.append(f"J{i} ({valor:.0f}°) está fuera de su rango real ({minimo}° a {maximo}°)")
    if problemas:
        return problemas  # con un ángulo imposible la geometría no tiene sentido
    brazo = puntos_del_brazo(angulos, largo_pinza)
    nombres = ("el hombro", "el codo", "la muñeca", "la muñeca", "la brida de la pinza")
    for etiqueta, punto in zip(nombres, brazo["articulaciones"][2:7]):
        if punto[2] < MARGEN_MESA:
            problemas.append(f"{etiqueta} quedaría a {punto[2] * 100:.0f} cm de la mesa (mínimo {MARGEN_MESA * 100:.0f} cm): atraviesa la mesa")
            break
    if brazo["cuerpo_pinza"][2] < MARGEN_MESA:
        problemas.append("el cuerpo de la pinza atraviesa la mesa")
    minimo_punta = punta_minima_para(z_tope_mm, largo_pinza)
    if brazo["punta"][2] < minimo_punta:
        problemas.append(f"la punta de los dedos quedaría {(minimo_punta - brazo['punta'][2]) * 100:.0f} cm por debajo del tablero")
    eslabones = brazo["eslabones"]
    for i in range(7):
        for j in range(i + 3, 7):
            if _distancia_entre_segmentos(*eslabones[i], *eslabones[j]) < DISTANCIA_MINIMA_ENTRE_ESLABONES:
                problemas.append(f"{NOMBRES_ESLABONES[i]} y {NOMBRES_ESLABONES[j]} chocarían entre sí")
    return problemas


def problemas_de_trayectoria(desde: list[float], hasta: list[float], z_tope_mm: float | None = None, largo_pinza: float = LARGO_PINZA_DEFECTO) -> list[str]:
    """Lo mismo que `problemas_de_pose` en el camino recto en articulaciones de `desde` a `hasta` (como lo recorre `MovJ`), muestreado cada
    `GRADOS_POR_MUESTRA` grados de la articulación que más se mueve. Cada problema trae el avance del camino donde aparece."""
    desde_np, hasta_np = np.asarray(desde, dtype=float), np.asarray(hasta, dtype=float)
    muestras = max(2, int(np.ceil(np.abs(hasta_np - desde_np).max() / GRADOS_POR_MUESTRA)))
    vistos: set[str] = set()
    problemas: list[str] = []
    for k in range(1, muestras + 1):
        avance = k / muestras
        for problema in problemas_de_pose(list(desde_np + (hasta_np - desde_np) * avance), z_tope_mm, largo_pinza):
            if problema not in vistos:
                vistos.add(problema)
                problemas.append(f"{problema} (a un {avance * 100:.0f}% del camino)")
    return problemas
