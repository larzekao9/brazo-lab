"""Ejemplo 5: mover una caja virtual de un lugar a otro.

Para correrlo en el brazo real solo cambia el destino (y pasa la celda del laboratorio):
    Brazo(destino="real", celda="celda/celda.json")
"""
from brazo_base import Brazo

with Brazo() as brazo:
    brazo.llevar("caja_roja", "bandeja")
    brazo.llevar("cilindro_azul", "tablero:e4")
    print("Listo. Objetos:", brazo.simulador.telemetria()["objetos"])
