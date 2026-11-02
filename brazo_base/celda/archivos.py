"""Leer y guardar la celda (`celda.json`).

Leer: un campo desconocido NO falla, se ignora y queda en `celda.avisos`. Guardar: siempre atómico (archivo temporal + renombrar) y con copia de
respaldo automática del archivo anterior (`celda.json.bak`).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import fields
from pathlib import Path

from brazo_base.celda.modelo import Celda, Objeto, Superficie
from brazo_base.errores import CeldaInvalida

CAMPOS_OBJETO = {f.name for f in fields(Objeto)}
CAMPOS_RAIZ = {"version", "nombre", "controlador", "herramienta", "seguridad", "mesa", "puntos", "superficies", "lugares", "objetos", "zonas_prohibidas"}
VERSION_ACTUAL = 1


def _numeros(valor, cantidad: int, donde: str) -> tuple[float, ...]:
    try:
        tupla = tuple(float(v) for v in valor)
    except (TypeError, ValueError):
        raise CeldaInvalida(f"{donde}: tiene que ser una lista de {cantidad} números") from None
    if len(tupla) != cantidad:
        raise CeldaInvalida(f"{donde}: tiene que tener {cantidad} números y tiene {len(tupla)}")
    return tupla


def _objeto(datos: dict, avisos: list[str]) -> Objeto:
    nombre = datos.get("nombre")
    if not nombre:
        raise CeldaInvalida("Hay un objeto sin «nombre»")
    desconocidos = sorted(set(datos) - CAMPOS_OBJETO)
    if desconocidos:
        avisos.append(f"Objeto «{nombre}»: campos desconocidos ignorados: {', '.join(desconocidos)}")
    limpio = {k: v for k, v in datos.items() if k in CAMPOS_OBJETO}
    limpio["posicion"] = _numeros(limpio.get("posicion", (0, 0, 0)), 3, f"Objeto «{nombre}»: posicion (x, y, z de la base)")
    if limpio.get("tamano_mm") is not None:
        limpio["tamano_mm"] = _numeros(limpio["tamano_mm"], 3, f"Objeto «{nombre}»: tamano_mm")
    return Objeto(**limpio)


def celda_desde_dict(datos: dict, ruta: str | None = None) -> Celda:
    """Arma una `Celda` desde el diccionario del JSON. Ignora campos desconocidos (con aviso)."""
    if not isinstance(datos, dict):
        raise CeldaInvalida("celda.json tiene que ser un objeto JSON")
    avisos: list[str] = []
    desconocidos = sorted(set(datos) - CAMPOS_RAIZ)
    if desconocidos:
        avisos.append(f"Campos desconocidos ignorados en la celda: {', '.join(desconocidos)}")
    if datos.get("version", VERSION_ACTUAL) > VERSION_ACTUAL:
        avisos.append(f"La celda es de una versión más nueva ({datos['version']}) que esta plataforma ({VERSION_ACTUAL}): puede que algo se ignore")
    celda = Celda(ruta=ruta, avisos=avisos)
    celda.nombre = str(datos.get("nombre", celda.nombre))
    celda.version = int(datos.get("version", VERSION_ACTUAL))
    celda.controlador = {**celda.controlador, **datos.get("controlador", {})}
    celda.herramienta = str(datos.get("herramienta", "ninguna"))
    celda.seguridad = {**celda.seguridad, **datos.get("seguridad", {})}
    celda.mesa = {**celda.mesa, **datos.get("mesa", {})}
    celda.puntos = dict(datos.get("puntos", {}))
    celda.lugares = dict(datos.get("lugares", {}))
    celda.zonas_prohibidas = list(datos.get("zonas_prohibidas", []))
    for nombre, s in datos.get("superficies", {}).items():
        try:
            celda.superficies[nombre] = Superficie(nombre, {k: tuple(float(x) for x in v[:2]) for k, v in s["esquinas"].items()}, float(s["z_mm"]), int(s["filas"]), int(s["columnas"]))
        except (KeyError, TypeError, ValueError) as error:
            raise CeldaInvalida(f"Superficie «{nombre}»: faltan o están mal los datos (esquinas, z_mm, filas, columnas): {error}") from error
    for d in datos.get("objetos", []):
        o = _objeto(d, avisos)
        celda.objetos[o.nombre] = o
    celda.validar()
    return celda


def cargar_herramienta(celda: Celda, carpeta: Path) -> None:
    """Lee `herramientas/<celda.herramienta>.json` junto a la celda (si existe) y lo deja en `celda.herramienta_config`."""
    if celda.herramienta == "ninguna":
        celda.herramienta_config = {"tipo": "ninguna", "largo_mm": 0.0}
        return
    archivo = carpeta / "herramientas" / f"{celda.herramienta}.json"
    if not archivo.exists():
        raise CeldaInvalida(f"La celda usa la herramienta «{celda.herramienta}» pero falta {archivo}. Creala (ver docs/agregar_una_herramienta.md) o poné «ninguna».")
    try:
        celda.herramienta_config = json.loads(archivo.read_text(encoding="utf-8"))
    except ValueError as error:
        raise CeldaInvalida(f"{archivo} no es un JSON válido: {error}") from error


def cargar_celda(ruta: str | Path) -> Celda:
    """Lee una celda y su herramienta. Falla con `CeldaInvalida` y un mensaje que dice qué arreglar."""
    ruta = Path(ruta)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except OSError as error:
        raise CeldaInvalida(f"No se pudo leer la celda {ruta}: {error}") from error
    except ValueError as error:
        raise CeldaInvalida(f"{ruta} no es un JSON válido: {error}") from error
    celda = celda_desde_dict(datos, str(ruta))
    cargar_herramienta(celda, ruta.parent)
    return celda


def celda_a_dict(celda: Celda) -> dict:
    return {
        "version": celda.version,
        "nombre": celda.nombre,
        "controlador": celda.controlador,
        "herramienta": celda.herramienta,
        "seguridad": celda.seguridad,
        "mesa": celda.mesa,
        "puntos": celda.puntos,
        "superficies": {n: {"esquinas": {k: list(v) for k, v in s.esquinas.items()}, "z_mm": s.z_mm, "filas": s.filas, "columnas": s.columnas} for n, s in celda.superficies.items()},
        "lugares": celda.lugares,
        "objetos": [{k: (list(v) if isinstance(v, tuple) else v) for k, v in vars(o).items() if v is not None} for o in celda.objetos.values()],
        "zonas_prohibidas": celda.zonas_prohibidas,
    }


def guardar_celda(celda: Celda, ruta: str | Path | None = None) -> Path:
    """Guarda de forma atómica y deja el archivo anterior como `.bak`. La celda se valida antes: si no sirve, no se toca el disco."""
    celda.validar()
    destino = Path(ruta or celda.ruta or "")
    if not str(destino) or destino.is_dir():
        raise CeldaInvalida("No sé dónde guardar la celda: pasá una ruta")
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(celda_a_dict(celda), ensure_ascii=False, indent=2) + "\n"
    descriptor, temporal = tempfile.mkstemp(dir=destino.parent, prefix=destino.name + ".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            archivo.write(texto)
            archivo.flush()
            os.fsync(archivo.fileno())
        if destino.exists():
            os.replace(destino, destino.with_name(destino.name + ".bak"))
        os.replace(temporal, destino)
    except BaseException:
        if os.path.exists(temporal):
            os.unlink(temporal)
        raise
    celda.ruta = str(destino)
    return destino
