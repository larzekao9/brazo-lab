"""Convierte la calibración real del ajedrez (brazo.json) en `celda/celda.json`.

    python herramientas/importar_calibracion_ajedrez.py ../Ajedrez/chessia-backend/calibracion_local/brazo.json

Solo LEE brazo.json. Escribe celda/celda.json (con copia .bak) y celda/herramientas/pinza_dh_dedos_largos.json.
"""
import argparse
import json
import sys
from pathlib import Path

from brazo_base.calibracion.ajedrez import celda_desde_brazo_json
from brazo_base.celda import cargar_celda, guardar_celda
from brazo_base.celda.archivos import celda_desde_dict

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("brazo_json", help="ruta a calibracion_local/brazo.json del ajedrez")
    p.add_argument("--salida", default=str(RAIZ / "celda" / "celda.json"))
    args = p.parse_args()
    celda_dict, herramienta = celda_desde_brazo_json(args.brazo_json)
    salida = Path(args.salida)
    (salida.parent / "herramientas").mkdir(parents=True, exist_ok=True)
    (salida.parent / "herramientas" / "pinza_dh_dedos_largos.json").write_text(json.dumps(herramienta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    celda = celda_desde_dict(celda_dict, str(salida))
    guardar_celda(celda, salida)
    cargar_celda(salida)  # comprobación: lo guardado se vuelve a leer y valida
    print(f"OK: {salida}  ({len(celda.perfiles) - 1} perfiles, {len(celda.lugares)} lugares, orientación {celda.orientacion})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
