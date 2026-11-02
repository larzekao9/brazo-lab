"""Ensayo SIN conectar con nada: muestra todas las poses que mandaría `llevar_desde` y comprueba zonas, límites y alcance del modelo.

    python herramientas/ensayar_pieza.py e2 e4            # peón (perfil p)
    python herramientas/ensayar_pieza.py g1 f3 n
    python herramientas/ensayar_pieza.py d8 cementerio:3 q
"""
import argparse
import sys
from pathlib import Path

from brazo_base.celda import cargar_celda
from brazo_base.seguridad import perfiles, validador
from brazo_base.seguridad.validador import Tramo
from brazo_base.simulador import cinematica

RAIZ = Path(__file__).resolve().parent.parent


def lugar(nombre: str, celda) -> str:
    return nombre if ":" in nombre or nombre in celda.lugares else f"{next(iter(celda.superficies))}:{nombre}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("desde")
    p.add_argument("hasta")
    p.add_argument("perfil", nargs="?", default="p")
    p.add_argument("--celda", default=str(RAIZ / "celda" / "celda.json"))
    args = p.parse_args()
    celda = cargar_celda(args.celda)
    poses = perfiles.Poses(celda)
    desde, hasta = lugar(args.desde, celda), lugar(args.hasta, celda)
    sobre = poses.traslado(args.perfil)
    secuencia = [("sobre el origen (MovJ)", poses.pose(desde, sobre, args.perfil)), ("baja despacio a agarrar", poses.pose_de_agarre(desde, args.perfil)),
                 ("sube despacio", poses.pose(desde, sobre, args.perfil)), ("sobre el destino", poses.pose(hasta, sobre, args.perfil)),
                 ("baja despacio a soltar", poses.pose_de_soltar(hasta, args.perfil)), ("sube despacio", poses.pose(hasta, sobre, args.perfil))]
    print(f"{desde} -> {hasta} con el perfil «{args.perfil}»: apertura {poses.apertura(args.perfil):.3f}, margen {poses.margen(args.perfil)} mm, giro {poses.giro(args.perfil)}°, traslado +{sobre} mm\n")
    semilla = tuple(celda.puntos["descanso"]["angulos"]) if "descanso" in celda.puntos else None
    for nombre, pose in secuencia:
        q = cinematica.angulos_para_pose_completa(pose, semilla)
        print(f"  {nombre:<26} x={pose[0]:8.1f} y={pose[1]:8.1f} z={pose[2]:7.1f}  rz={pose[5]:7.1f}   alcance del modelo: {'sí' if q else 'NO'}")
        semilla = q or semilla
    previo = tuple(celda.puntos["descanso"].get("pose", secuencia[0][1])[:3])
    tramos = [Tramo(a[1][:3], b[1][:3], "ensayo") for a, b in zip(secuencia, secuencia[1:])]
    problemas = validador.problemas_de_tramos(tramos, celda)
    print("\nZonas y límites:", "sin problemas" if not problemas else "\n  - " + "\n  - ".join(problemas))
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
