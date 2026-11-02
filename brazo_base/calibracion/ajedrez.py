"""Importa la calibración REAL del ajedrez (`calibracion_local/brazo.json`) como celda de `brazo-base`, sin perder ningún valor medido.

El archivo se LEE, nunca se escribe. Lo que sale es un diccionario de celda en modo «brida» con la orientación enseñada, la superficie del tablero
(con el corrimiento y el marco), los perfiles de agarre por tipo de pieza y los lugares del cementerio y la reserva. Con esa celda,
`Brazo.llevar_desde` hace lo mismo que el `EjecutorReal` del ajedrez.
"""
from __future__ import annotations

import json
from pathlib import Path

from brazo_base.errores import CeldaInvalida

PIEZAS = ("p", "n", "b", "r", "q", "k")
LUGARES_POR_CEMENTERIO = 32
"""Cuántos lugares `cementerio:N` (y `cementerio_jugador:N`) se generan: más que las 15 piezas que se pueden capturar de un color."""


def _cuadricula(origen, paso, paso_fila, columnas: int, indice: int) -> tuple[float, float]:
    fila, columna = divmod(indice, max(1, columnas))
    return origen[0] + columna * paso[0] + fila * paso_fila[0], origen[1] + columna * paso[1] + fila * paso_fila[1]


def celda_desde_brazo_json(ruta: str | Path, nombre: str = "Laboratorio FICCT - Dobot CR5AS") -> tuple[dict, dict]:
    """`(celda, herramienta)`: los diccionarios de `celda.json` y de `herramientas/pinza_dh_dedos_largos.json`."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CeldaInvalida(f"No se pudo leer la calibración {ruta}: {error}") from error
    return celda_desde_datos(datos, nombre)


def celda_desde_datos(d: dict, nombre: str = "Laboratorio FICCT - Dobot CR5AS") -> tuple[dict, dict]:
    """Lo mismo que `celda_desde_brazo_json` con el contenido del archivo ya leído (`angulos_cero`, `puntos` y `agarre`)."""
    try:
        puntos, a = d["puntos"], d["agarre"]
        cero = d["angulos_cero"]
    except (KeyError, TypeError) as error:
        raise CeldaInvalida(f"La calibración no tiene el campo {error}: hace falta angulos_cero, puntos y agarre") from error
    if a.get("z_tope") is None:
        raise CeldaInvalida("La calibración no tiene z_tope (la altura del tablero): medila apoyando las puntas de los dedos")

    margen_defecto = float(a.get("margen_agarre_mm", 3.0))
    giro_defecto = float(a.get("giro_diagonal_grados", 45.0))
    perfiles: dict[str, dict] = {}
    for pieza in PIEZAS:
        if pieza == "p":
            apertura = a.get("aperturas_por_pieza", {}).get("p", a["apertura_aproximacion"])
        elif pieza in a.get("aperturas_por_pieza", {}):
            apertura = a["aperturas_por_pieza"][pieza]
        else:
            continue  # sin apertura medida no hay perfil: bajar con una apertura chica puede romper la pieza
        perfil = {"margen_mm": float(a.get("margenes_por_pieza", {}).get(pieza, margen_defecto)), "apertura": apertura / 1000.0, "giro_grados": float(a.get("giros_por_pieza", {}).get(pieza, giro_defecto))}
        if pieza in a.get("alturas_piezas_mm", {}):
            perfil["alto_mm"] = float(a["alturas_piezas_mm"][pieza])
        perfiles[pieza] = perfil
    perfiles["defecto"] = dict(perfiles["p"])

    desnivel = float(a.get("desnivel_cementerio_mm", 0.0))
    lugares: dict[str, dict] = {}
    if a.get("cementerio_origen"):
        for i in range(LUGARES_POR_CEMENTERIO):
            x, y = _cuadricula(a["cementerio_origen"], a["cementerio_paso"], a["cementerio_paso_fila"], a["cementerio_columnas"], i)
            lugares[f"cementerio:{i}"] = {"x": x, "y": y, "desnivel_mm": desnivel}
    if a.get("cementerio_jugador_origen") or a.get("cementerio_origen"):
        por_jugador = bool(a.get("cementerio_jugador_origen"))
        origen = a["cementerio_jugador_origen"] if por_jugador else a["cementerio_origen"]
        paso = a["cementerio_jugador_paso"] if por_jugador else a["cementerio_paso"]
        paso_fila = a["cementerio_jugador_paso_fila"] if por_jugador else a["cementerio_paso_fila"]
        for i in range(LUGARES_POR_CEMENTERIO):
            x, y = _cuadricula(origen, paso, paso_fila, a["cementerio_columnas"], i)
            lugares[f"cementerio_jugador:{i}"] = {"x": x, "y": y, "desnivel_mm": desnivel}
    for lugar, (x, y) in a.get("cementerio_lugares", {}).items():  # un lugar enseñado con una pieza real gana a la cuadrícula
        lugares[lugar] = {"x": x, "y": y, "desnivel_mm": desnivel}
    for nombre_reserva, (x, y) in a.get("reservas", {}).items():
        lugares[f"reserva:{nombre_reserva}"] = {"x": x, "y": y}

    esquinas = {c: [puntos[c][0], puntos[c][1]] for c in ("a1", "h1", "a8", "h8") if c in puntos}
    celda = {
        "version": 1,
        "nombre": nombre,
        "controlador": {"host": "192.168.5.1", "puerto": 29999},
        "herramienta": "pinza_dh_dedos_largos",
        "modo_pose": "brida",
        "orientacion": list(puntos["a1"][3:]),
        "seguridad": {"velocidad_maxima_real": max(50, int(a.get("velocidad_global", 20))), "limites_mesa": a.get("limites_mesa"), "altura_minima_mm": 5, "altura_segura_mm": float(a.get("altura_segura_mm", 80.0))},
        "mesa": {"z_mm": 0},
        "puntos": {"descanso": {"angulos": list(cero)}, **{c: {"pose": list(p)} for c, p in puntos.items()}},
        "superficies": {"tablero_ajedrez": {"esquinas": esquinas, "z_mm": a["z_tope"], "filas": 8, "columnas": 8, "corrimiento_mm": [a.get("corrimiento_x_mm", 0.0), a.get("corrimiento_y_mm", 0.0)], "borde_mm": a.get("altura_borde_mm", 0.0)}},
        "lugares": lugares,
        "objetos": [],
        "zonas_prohibidas": list(a.get("zonas_prohibidas", [])),
        "agarre": {
            "z_referencia_mm": a["z_tope"], "margen_agarre_mm": margen_defecto, "giro_grados": giro_defecto,
            "altura_segura_mm": float(a.get("altura_segura_mm", 80.0)), "holgura_traslado_mm": float(a.get("holgura_traslado_mm", 15.0)),
            "velocidad_bajada": int(a.get("velocidad_bajada", 10)), "aceleracion_bajada": int(a.get("aceleracion_bajada", 5)),
            "elevacion_al_soltar_mm": float(a.get("elevacion_al_soltar_mm", 0.0)), "desnivel_cementerio_mm": desnivel,
            "holgura_cementerio_mm": float(a.get("holgura_cementerio_mm", 2.0)), "apertura_extra_soltar": a.get("apertura_extra_soltar", 250) / 1000.0,
            "velocidad_global": int(a.get("velocidad_global", 20)), "aceleracion": int(a.get("aceleracion", 10)), "velocidad": int(a.get("velocidad", 20)),
        },
        "perfiles": perfiles,
    }
    herramienta = {"tipo": "pinza_dh", "largo_mm": float(a.get("largo_pinza_mm", 217.0)), "fuerza": int(a.get("fuerza", 20)), "velocidad": int(a.get("velocidad_pinza", 20)), "carrera_mm": 26}
    return celda, herramienta


def celda_de_ajedrez(datos: dict, nombre: str = "Laboratorio FICCT - Dobot CR5AS"):
    """La `Celda` lista para `Brazo` a partir del contenido de `calibracion_local/brazo.json` (sin pasar por archivos)."""
    from brazo_base.celda.archivos import celda_desde_dict

    celda_dict, herramienta = celda_desde_datos(datos, nombre)
    celda = celda_desde_dict(celda_dict)
    celda.herramienta_config = herramienta
    return celda
