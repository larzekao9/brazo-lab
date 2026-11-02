"""Ejemplo 7: guardar una rutina (pasos con nombre) y ejecutarla.

Una rutina solo se acepta para el brazo real si ya corrió completa en el simulador con exactamente esos pasos. Se guardan en ~/.brazo-base/rutinas con la celda de práctica.
"""
from brazo_base import Brazo

with Brazo() as brazo:
    a = [round(v, 3) for v in brazo.angulos()]
    giro = [a[0] + 15] + a[1:]
    brazo.rutinas.guardar("saludo", [
        {"tipo": "articulaciones", "angulos": giro, "velocidad": 40},
        {"tipo": "pinza", "apertura": 300},
        {"tipo": "esperar", "segundos": 0.5},
        {"tipo": "pinza", "apertura": 1000},
        {"tipo": "articulaciones", "angulos": a, "velocidad": 40},
    ])
    print("¿validada para el brazo real?", brazo.rutinas.obtener("saludo")["validada"])  # todavía no
    brazo.ejecutar_rutina("saludo", avance=lambda i, n, texto: print(f"  paso {i}/{n}: {texto}"))
    print("¿validada para el brazo real?", brazo.rutinas.obtener("saludo")["validada"])  # ahora sí
