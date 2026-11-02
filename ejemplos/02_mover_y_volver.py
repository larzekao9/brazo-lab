"""Ejemplo 2: mover el brazo y volver al punto de descanso."""
from brazo_base import Brazo

with Brazo() as brazo:
    brazo.mover_a(x=0, y=-500, z=150)  # mm, en la punta de la herramienta
    brazo.mover_relativo(dz=-50)
    print("Llegué a", brazo.pose())
    brazo.ir_a("descanso")
