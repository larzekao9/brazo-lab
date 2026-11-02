"""Asistente: una superficie con cuadrícula a partir de 3 o 4 esquinas enseñadas con el brazo (generaliza la calibración del tablero del ajedrez).

Se lleva la herramienta al centro de las casillas `a1`, `h1` y `a8` (y `h8`, opcional) y se anota la pose de cada una (`GetPose()`, o el panel). Se valida igual que el
ajedrez: la orientación de la herramienta tiene que ser parecida en todas, `h1` y `a8` no pueden estar muy por encima de `a1` (la altura de la superficie se toma de `a1`,
que se enseña apoyando la herramienta con cuidado) y después de ajustar la cuadrícula se avisa de cada esquina que quedó lejos de donde se enseñó.
"""
from __future__ import annotations

from collections.abc import Sequence

from brazo_base.celda.modelo import Superficie
from brazo_base.errores import CeldaInvalida

ESQUINAS_OBLIGATORIAS = ("a1", "h1", "a8")
ESQUINAS_OPCIONALES = ("h8",)
TOLERANCIA_INCLINACION_GRADOS = 10.0
TOLERANCIA_GIRO_GRADOS = 30.0
ALTURA_MAXIMA_SOBRE_A1_MM = 60.0
MARGEN_POR_DEBAJO_DE_A1_MM = 5.0
RESIDUO_AVISO_MM = 4.0
AREA_MINIMA_MM2 = 1000.0


def _diferencia_angular(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def calibrar_superficie(nombre: str, puntos: dict[str, Sequence[float]], filas: int, columnas: int, z_mm: float | None = None,
                        corrimiento_mm: tuple[float, float] = (0.0, 0.0), borde_mm: float = 0.0) -> tuple[Superficie, list[str]]:
    """`(superficie, avisos)`. Cada punto es una pose `(x, y, z, rx, ry, rz)` (se comprueba la orientación) o solo `(x, y)` / `(x, y, z)`.

    Sin `z_mm`, la altura es la `z` de `a1` (hace falta que se haya enseñado con `z`).

    Raises:
        CeldaInvalida: faltan esquinas, hay un dato mal, las orientaciones no coinciden, `h1` o `a8` se enseñaron muy por encima de `a1` o las esquinas son colineales.
    """
    esquinas = set(puntos)
    if not set(ESQUINAS_OBLIGATORIAS) <= esquinas <= set(ESQUINAS_OBLIGATORIAS + ESQUINAS_OPCIONALES):
        raise CeldaInvalida(f"Hay que enseñar las esquinas {', '.join(ESQUINAS_OBLIGATORIAS)} (y, si querés, {', '.join(ESQUINAS_OPCIONALES)}); llegaron {', '.join(sorted(esquinas)) or 'ninguna'}")
    for esquina, p in puntos.items():
        if len(p) not in (2, 3, 6) or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in p):
            raise CeldaInvalida(f"La esquina {esquina} tiene que ser una pose (x, y, z, rx, ry, rz) o (x, y[, z]) en números")
    avisos: list[str] = []
    con_pose = {e: p for e, p in puntos.items() if len(p) == 6}
    if len(con_pose) >= 2:
        ref = con_pose.get("a1") or next(iter(con_pose.values()))
        for esquina, p in con_pose.items():
            inclinacion = max(_diferencia_angular(a, b) for a, b in zip(p[3:5], ref[3:5]))
            giro = _diferencia_angular(p[5], ref[5])
            if inclinacion > TOLERANCIA_INCLINACION_GRADOS or giro > TOLERANCIA_GIRO_GRADOS:
                raise CeldaInvalida(f"La orientación de la herramienta en {esquina} {tuple(round(v, 1) for v in p[3:])} difiere demasiado de la de a1 {tuple(round(v, 1) for v in ref[3:])}: volvé a enseñarla con la herramienta apuntando igual a la superficie")
    alturas = {e: p[2] for e, p in puntos.items() if len(p) >= 3}
    if z_mm is None:
        if "a1" not in alturas:
            raise CeldaInvalida("Falta la altura de la superficie: enseñá a1 con su z (la pose completa) o pasá z_mm")
        z_mm = alturas["a1"]
    for esquina in ("h1", "a8"):
        if esquina in alturas and "a1" in alturas:
            if alturas[esquina] - alturas["a1"] > ALTURA_MAXIMA_SOBRE_A1_MM:
                raise CeldaInvalida(f"{esquina} se enseñó {alturas[esquina] - alturas['a1']:.0f} mm por encima de a1 (máximo {ALTURA_MAXIMA_SOBRE_A1_MM:.0f} mm): bajá la herramienta para que la posición lateral sea precisa")
            if alturas["a1"] - alturas[esquina] > MARGEN_POR_DEBAJO_DE_A1_MM:
                avisos.append(f"{esquina} quedó {alturas['a1'] - alturas[esquina]:.1f} mm por DEBAJO de a1: la altura se toma de a1; si a1 quedó demasiado arriba la herramienta no llegaría a los objetos. Comprobalo bajando sobre a1.")
    a1, h1, a8 = (puntos[e] for e in ESQUINAS_OBLIGATORIAS)
    area = abs((h1[0] - a1[0]) * (a8[1] - a1[1]) - (h1[1] - a1[1]) * (a8[0] - a1[0]))
    if area < AREA_MINIMA_MM2:
        raise CeldaInvalida(f"Las esquinas a1, h1 y a8 son casi colineales sobre la mesa (el triángulo que forman mide {area:.0f} mm²): no definen una superficie. Revisá que enseñaste tres esquinas distintas")
    superficie = Superficie(nombre, {e: (float(p[0]), float(p[1])) for e, p in puntos.items()}, float(z_mm), int(filas), int(columnas), tuple(float(v) for v in corrimiento_mm), float(borde_mm))
    superficie.validar()
    for esquina, p in puntos.items():
        columna, fila = superficie._columna_fila(esquina)
        x, y = superficie.centro(columna, fila)
        residuo = ((x - p[0]) ** 2 + (y - p[1]) ** 2) ** 0.5
        if residuo > RESIDUO_AVISO_MM:
            avisos.append(f"{esquina} quedó a {residuo:.1f} mm de donde la cuadrícula ajustada la pone: revisá si está bien centrada")
    return superficie, avisos
