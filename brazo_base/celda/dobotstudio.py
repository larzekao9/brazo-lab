"""Importar el `point.json` de un proyecto de DobotStudio Pro: cada punto con alias pasa a ser un punto con nombre de la celda."""
from __future__ import annotations

import json
from pathlib import Path

from brazo_base.errores import CeldaInvalida


def puntos_desde_dobotstudio(ruta: str | Path) -> dict[str, dict]:
    """Devuelve `{alias_en_minusculas: {"pose": [...], "angulos": [...]}}` con todos los puntos que tienen alias.

    Solo se aceptan puntos con `tool` y `user` en 0 (con otro sistema de coordenadas las poses no serían comparables). Los puntos sin alias se
    ignoran. Si dos puntos tienen el mismo alias (sin distinguir mayúsculas) gana el último y se avisa en el mensaje del error de duplicados.
    """
    try:
        registros = json.loads(Path(ruta).read_text(encoding="utf-8"))
        if not isinstance(registros, list):
            raise TypeError("se esperaba una lista de puntos")
    except (OSError, ValueError, TypeError) as error:
        raise CeldaInvalida(f"No se pudo leer {ruta}: ¿es el point.json de un proyecto de DobotStudio Pro?") from error
    puntos: dict[str, dict] = {}
    for registro in registros:
        alias = str(registro.get("alias", "")).strip().lower() if isinstance(registro, dict) else ""
        if not alias:
            continue
        if alias in puntos:
            raise CeldaInvalida(f"El alias «{alias}» está repetido en {ruta}: dejá un solo punto con ese alias")
        if registro.get("tool", 0) != 0 or registro.get("user", 0) != 0:
            raise CeldaInvalida(f"El punto «{alias}» usa tool={registro.get('tool')} y user={registro.get('user')}: tiene que ser 0 y 0")
        punto: dict = {}
        if registro.get("pose"):
            punto["pose"] = [float(v) for v in registro["pose"]]
        if registro.get("joint"):
            punto["angulos"] = [float(v) for v in registro["joint"]]
        if punto:
            puntos[alias] = punto
    return puntos


def importar_en_celda(celda, ruta: str | Path, reemplazar: bool = False) -> list[str]:
    """Agrega los puntos del archivo a `celda.puntos`. No pisa uno que ya existe salvo `reemplazar=True`. Devuelve los nombres agregados."""
    agregados = []
    for nombre, punto in puntos_desde_dobotstudio(ruta).items():
        if nombre in celda.puntos and not reemplazar:
            continue
        celda.puntos[nombre] = punto
        agregados.append(nombre)
    return agregados
