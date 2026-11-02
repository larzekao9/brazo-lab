"""Compara el modelo del brazo (URDF) con lo que el controlador dice: SOLO LECTURA, no habilita ni mueve nada.

Lee `GetAngle()` y `GetPose()` y calcula con la cinemática del URDF qué pose deberían dar esos ángulos. Si coinciden, los ángulos del controlador
significan lo mismo que los del modelo (el simulador, la validación por ángulos y el dibujo 3D son fieles). Si no, anotá la diferencia: hay que ajustar el
signo o el desfase de alguna articulación (`brazo_base/simulador/cinematica.py`).

Mové el brazo a mano (modo arrastre en DobotStudio) a 4 o 5 posturas distintas y corré el script en cada una.

    python herramientas/verificar_geometria.py --host 192.168.5.1
"""
import argparse
import sys

from brazo_base.simulador import cinematica

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from probar_conexion import consultar  # noqa: E402

TOLERANCIA_MM = 2.0
TOLERANCIA_GRADOS = 1.0


def numeros(texto: str) -> list[float]:
    return [float(v) for v in texto.replace("{", "").replace("}", "").split(",") if v.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="192.168.5.1")
    p.add_argument("--puerto", type=int, default=29999)
    args = p.parse_args()
    try:
        r = consultar(args.host, args.puerto, 3.0, ("GetAngle()", "GetPose()"))
    except OSError as error:
        print(f"No se pudo conectar: {error}")
        return 1
    angulos, real = numeros(r["GetAngle()"]["valores"]), numeros(r["GetPose()"]["valores"])
    modelo = cinematica.pose_para_angulos(tuple(angulos))
    print("Ángulos del controlador :", [round(a, 3) for a in angulos])
    print("Pose del controlador    :", [round(v, 2) for v in real])
    print("Pose según el URDF      :", [round(v, 2) for v in modelo])
    dpos = [m - r_ for m, r_ in zip(modelo[:3], real[:3])]
    drot = [((m - r_ + 180) % 360) - 180 for m, r_ in zip(modelo[3:], real[3:])]
    print("Diferencia (mm)         :", [round(v, 2) for v in dpos])
    print("Diferencia (grados)     :", [round(v, 2) for v in drot])
    bien = max(abs(v) for v in dpos) < TOLERANCIA_MM and max(abs(v) for v in drot) < TOLERANCIA_GRADOS
    print("\nCOINCIDEN: el modelo es fiel en esta postura." if bien else "\nNO COINCIDEN: copiá esta salida en docs/bitacora.md. Posible causa: signo o desfase de una articulación, o la convención de los ángulos de Euler.")
    return 0 if bien else 3


if __name__ == "__main__":
    sys.exit(main())
