"""Ejemplo 1: conectar con el brazo virtual y ver dónde está."""
from brazo_base import Brazo

with Brazo() as brazo:  # simulador por defecto: no toca ningún brazo real
    print("Pose del TCP (x, y, z, rx, ry, rz):", brazo.pose())
    print("Ángulos:", brazo.angulos())
    print("Estado:", brazo.estado())
