"""Valida un plan completo ANTES de mandar el primer comando: límites de la mesa, zonas prohibidas, altura mínima y límites de articulación."""
from __future__ import annotations

from dataclasses import dataclass

from brazo_base.errores import RecorridoProhibido
from brazo_base.seguridad import geometria, zonas

Punto = tuple[float, float, float]


@dataclass
class Tramo:
    """Un tramo recto de la punta (TCP) de `desde` a `hasta`, en mm."""

    desde: Punto
    hasta: Punto
    etiqueta: str = ""


def problemas_de_tramos(tramos: list[Tramo], celda) -> list[str]:
    """Todos los problemas del recorrido (vacío = se puede)."""
    problemas: list[str] = []
    zonas_celda = _Parametros(celda.zonas_efectivas, celda.limites_mesa)
    for tramo in tramos:
        for punto in (tramo.desde, tramo.hasta):
            if punto[2] < celda.mesa_z_mm + celda.altura_minima_mm - 1e-6:
                problemas.append(f"{tramo.etiqueta or 'tramo'}: z={punto[2]:.0f} mm queda por debajo de la altura mínima ({celda.mesa_z_mm + celda.altura_minima_mm:.0f} mm)")
        for problema in zonas.problemas_de_tramo(tramo.desde, tramo.hasta, zonas_celda):
            problemas.append(f"{tramo.etiqueta or 'tramo'}: {problema}")
    return list(dict.fromkeys(problemas))


def exigir_tramos(tramos: list[Tramo], celda) -> None:
    """`RecorridoProhibido` si algo no cumple; no mueve nada."""
    problemas = problemas_de_tramos(tramos, celda)
    if problemas:
        raise RecorridoProhibido(problemas)


def exigir_articulaciones(desde: list[float] | None, hasta: list[float], celda) -> None:
    """Valida un movimiento por ángulos: límites, mesa, choques entre eslabones y zonas con TODO el brazo."""
    largo = celda.largo_herramienta_mm / 1000 if celda.largo_herramienta_mm else geometria.LARGO_PINZA_DEFECTO
    problemas = geometria.problemas_de_pose(hasta, None, largo)
    if desde is not None and not problemas:
        problemas = geometria.problemas_de_trayectoria(desde, hasta, None, largo)
    if not problemas:
        problemas = zonas.problemas_de_brazo(hasta, _Parametros(celda.zonas_efectivas, celda.limites_mesa), largo)
    if problemas:
        raise RecorridoProhibido(list(dict.fromkeys(problemas)))


@dataclass
class _Parametros:
    zonas_prohibidas: list
    limites_mesa: list | None
