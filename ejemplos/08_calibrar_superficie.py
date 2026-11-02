"""Ejemplo 8: calibrar una superficie con cuadrícula a partir de 3 esquinas enseñadas (no necesita el brazo).

En el laboratorio las poses salen de `brazo.pose()` con la herramienta en el centro de cada esquina (o del botón «Capturar» del panel).
"""
from brazo_base.calibracion.superficie import calibrar_superficie

esquinas = {
    "a1": (-120.25, -674.2, 225.0, 177.8, -2.4, -82.1),   # x, y, z, rx, ry, rz
    "h1": (171.8, -679.7, 224.2, 177.8, -2.1, -58.0),
    "a8": (-119.7, -372.7, 221.5, 179.5, -3.3, -80.6),
}
superficie, avisos = calibrar_superficie("tablero", esquinas, filas=8, columnas=8)
print("altura de la superficie:", superficie.z_mm)
for casilla in ("a1", "e4", "h8"):
    x, y, z = superficie.lugar(casilla)
    print(f"  {casilla}: x={x:.1f} y={y:.1f} z={z:.1f}")
print("avisos:", avisos or "ninguno")
