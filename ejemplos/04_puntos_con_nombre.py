"""Ejemplo 4: puntos y lugares con nombre de la celda."""
from brazo_base import Brazo

with Brazo() as brazo:
    print("Puntos:", list(brazo.celda.puntos))
    print("Lugares:", list(brazo.celda.lugares), "| superficies:", list(brazo.celda.superficies))
    brazo.ir_a("bandeja")  # arriba de la bandeja, a la altura segura
    brazo.ir_a("tablero:e4")  # cualquier casilla de una superficie
    brazo.ir_a("descanso")
