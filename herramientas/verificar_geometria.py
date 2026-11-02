"""Compara el modelo del brazo (el del simulador y el dibujo 3D) con el propio controlador: SOLO LECTURA, no habilita ni mueve nada.

1. Para 7 posturas de prueba le pide al controlador `PositiveKin(...)` (un cálculo: no mueve el brazo, sirve aunque esté apagado en modo TCP/IP) la pose que da cada
   juego de ángulos y la compara con la del modelo.
2. Con los ángulos actuales compara `GetPose()` con el modelo (mové el brazo a mano a otras posturas y repetí).

Si coinciden, los ángulos del controlador significan lo mismo que los del modelo. Si no, el script dice si la diferencia es solo un giro de la base (el radio y la altura
coinciden: hay que girar `MAPA_GLB` en `brazo_base/simulador/cinematica.py`) o algo más (copiá la salida en docs/bitacora.md).

    python herramientas/verificar_geometria.py --host 192.168.5.1
"""
import argparse
import math
import socket
import sys

from brazo_base.simulador import cinematica

TOLERANCIA_MM = 2.0
TOLERANCIA_GRADOS = 1.0
POSTURAS = ((0, 0, 90, 0, 90, 0), (0, 0, 0, 0, 0, 0), (30, -20, 60, 20, 80, 0), (-45, 30, -90, 0, 90, 45), (90, 10, 50, -30, 60, -60), (-120, 60, 20, 45, -70, 90), (298.4786, 35.3395, -150.676, 27.4337, 90.4496, -38.7623))
PERMITIDOS = ("GetAngle(", "GetPose(", "RobotMode(", "PositiveKin(")  # solo consultas: ninguna mueve ni habilita el brazo


def consultar(conexion: socket.socket, comando: str) -> list[float]:
    if not comando.startswith(PERMITIDOS):
        raise ValueError(f"Solo se permiten consultas; no se enviará {comando!r}")
    conexion.sendall(comando.encode("ascii"))
    texto = conexion.recv(1024).decode("ascii", errors="replace").strip().rstrip(";")
    if "Control Mode Is Not Tcp" in texto:
        raise RuntimeError("El robot responde pero NO está en modo TCP/IP: activalo en DobotStudio Pro")
    error, _, resto = texto.partition(",")
    if error.strip() != "0":
        raise RuntimeError(f"{comando} -> {texto}")
    valores = resto[resto.index("{") + 1 : resto.index("}")]
    return [float(v) for v in valores.split(",") if v.strip()]


def comparar(nombre: str, angulos, real) -> bool:
    modelo = cinematica.pose_para_angulos(tuple(angulos))
    dpos = [m - r for m, r in zip(modelo[:3], real[:3])]
    drot = [((m - r + 180) % 360) - 180 for m, r in zip(modelo[3:], real[3:])]
    bien = max(abs(v) for v in dpos) < TOLERANCIA_MM and max(abs(v) for v in drot) < TOLERANCIA_GRADOS
    print(f"\n{nombre}: ángulos {[round(a, 1) for a in angulos]}")
    print(f"   controlador {[round(v, 1) for v in real]}\n   modelo      {[round(v, 1) for v in modelo]}   -> {'COINCIDEN' if bien else 'NO coinciden'}")
    if not bien:
        radio_real, radio_modelo = math.hypot(*real[:2]), math.hypot(*modelo[:2])
        if abs(radio_real - radio_modelo) < TOLERANCIA_MM and abs(real[2] - modelo[2]) < TOLERANCIA_MM:
            giro = (math.degrees(math.atan2(real[1], real[0]) - math.atan2(modelo[1], modelo[0])) + 180) % 360 - 180
            print(f"   el radio ({radio_real:.1f}) y la altura ({real[2]:.1f}) coinciden: es solo un giro de la base de {giro:.1f}°")
    return bien


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="192.168.5.1")
    p.add_argument("--puerto", type=int, default=29999)
    args = p.parse_args()
    try:
        with socket.create_connection((args.host, args.puerto), timeout=3) as conexion:
            conexion.settimeout(3)
            resultados = [comparar(f"Postura {i}", q, consultar(conexion, f"PositiveKin({','.join(f'{a:g}' for a in q)},user=0,tool=0)")) for i, q in enumerate(POSTURAS, start=1)]
            actuales = consultar(conexion, "GetAngle()")
            resultados.append(comparar("Postura actual del brazo", actuales, consultar(conexion, "GetPose()")))
    except (OSError, RuntimeError) as error:
        print(f"No se pudo: {error}")
        return 1
    print(f"\n{sum(resultados)} de {len(resultados)} coinciden.")
    print("El modelo es fiel." if all(resultados) else "El modelo NO coincide con el controlador: el brazo real no se afecta (usa el controlador), pero el simulador y el dibujo 3D hay que ajustarlos. Copiá esta salida en docs/bitacora.md.")
    return 0 if all(resultados) else 3


if __name__ == "__main__":
    sys.exit(main())
