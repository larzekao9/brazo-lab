"""Mueve UNA pieza con el brazo REAL (agarrar en `desde`, soltar en `hasta`). Es lo que hace el ajedrez, sin ajedrez.

Es la primera prueba con movimiento: usá una velocidad baja (--velocidad 10) y la mano cerca del botón de paro. No hace nada si falta la confirmación.

    python herramientas/mover_pieza.py e2 e4 p --velocidad 10 --confirmo-el-brazo-real
"""
import argparse
import sys
from pathlib import Path

from brazo_base import Brazo, ErrorBrazo

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("desde")
    p.add_argument("hasta")
    p.add_argument("perfil", nargs="?", default="p")
    p.add_argument("--celda", default=str(RAIZ / "celda" / "celda.json"))
    p.add_argument("--velocidad", type=int, default=10, help="SpeedFactor global (1 a 100). Por defecto 10")
    p.add_argument("--confirmo-el-brazo-real", action="store_true", help="obligatorio: el brazo se va a mover")
    args = p.parse_args()
    if not args.confirmo_el_brazo_real:
        print("Falta --confirmo-el-brazo-real: este script MUEVE el brazo real. Probá antes herramientas/ensayar_pieza.py (no conecta con nada).")
        return 2
    brazo = Brazo(destino="real", celda=args.celda, velocidad=args.velocidad)
    desde, hasta = (n if ":" in n or n in brazo.celda.lugares else f"{next(iter(brazo.celda.superficies))}:{n}" for n in (args.desde, args.hasta))
    try:
        brazo.conectar()
        print("Conectado. Habilitando (el brazo enciende y suelta los frenos; no se mueve)…")
        brazo.habilitar()
        print(f"Moviendo {desde} -> {hasta} (perfil {args.perfil}, velocidad {brazo.velocidad} %)…")
        brazo.llevar_desde(desde, hasta, args.perfil)
        print("Listo.")
        return 0
    except ErrorBrazo as error:
        print(f"\nSE DETUVO: {error}")
        brazo.parar()
        return 1
    except KeyboardInterrupt:
        brazo.parar()
        print("\nParado por el usuario.")
        return 130
    finally:
        brazo.desconectar()  # no deshabilita el brazo


if __name__ == "__main__":
    sys.exit(main())
