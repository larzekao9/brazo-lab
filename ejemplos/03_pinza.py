"""Ejemplo 3: abrir y cerrar la pinza."""
from brazo_base import Brazo

with Brazo() as brazo:
    brazo.herramienta.abrir()
    brazo.herramienta.abrir_a(0.5)  # 0 cerrada, 1 abierta
    print("¿Sostiene algo?", brazo.herramienta.cerrar())  # sin objeto: False
