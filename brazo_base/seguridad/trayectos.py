"""Alturas de viaje de un pick and place (corrige el error del ajedrez: la base del objeto que se lleva quedaba más baja de lo pedido)."""
from __future__ import annotations

HOLGURA_VIAJE_MM = 20.0


def alto_maximo_de_objetos(celda, excepto: str | None = None) -> float:
    """Altura (z) del punto más alto que hay que pasar POR ENCIMA: la mesa y el tope de cada objeto agarrable salvo `excepto` (el que se lleva).

    Los objetos fijos (un trípode) no cuentan: no se sobrevuelan, se esquivan, y de eso se ocupan las zonas prohibidas que generan.
    """
    tope = celda.mesa_z_mm
    for o in celda.objetos.values():
        if o.nombre != excepto and o.agarrable:
            tope = max(tope, o.posicion[2] + o.alto)
    return tope


def altura_de_traslado(celda, alto_maximo_mm: float, agarre_sobre_base_mm: float = 0.0, holgura_mm: float = HOLGURA_VIAJE_MM) -> float:
    """Z del TCP para viajar sin chocar: `max(altura_segura, alto_maximo + holgura + lo que la base del objeto cuelga bajo el TCP)`.

    Con `agarre_sobre_base_mm` (cuánto más arriba que la base del objeto está el TCP al agarrarlo) la BASE del objeto que se lleva pasa a `holgura_mm`
    por encima del punto más alto, en vez de lo que quedaba por restar el margen de agarre.
    """
    return max(celda.altura_segura_mm, alto_maximo_mm + holgura_mm + agarre_sobre_base_mm)
