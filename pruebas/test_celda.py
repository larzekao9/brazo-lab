import json

import pytest

from brazo_base import CeldaInvalida, celda_demo
from brazo_base.celda import cargar_celda, guardar_celda
from brazo_base.celda.archivos import celda_desde_dict
from brazo_base.celda.dobotstudio import importar_en_celda, puntos_desde_dobotstudio


def test_la_celda_demo_carga_y_valida():
    celda = celda_demo()
    assert celda.largo_herramienta_mm == 217
    assert {"caja_roja", "cilindro_azul", "tripode_camara"} <= set(celda.objetos)


def test_superficie_da_lugares_por_casilla():
    celda = celda_demo()
    assert celda.posicion_de("tablero:a1") == pytest.approx((-105, -640, 0))
    assert celda.posicion_de("tablero:h8") == pytest.approx((105, -430, 0))
    x, y, _ = celda.posicion_de("tablero:e4")
    assert (x, y) == pytest.approx((15, -550))


def test_lugar_desconocido_dice_cuales_hay():
    with pytest.raises(CeldaInvalida, match="bandeja"):
        celda_demo().posicion_de("no_existe")


def test_casilla_fuera_de_la_superficie():
    with pytest.raises(CeldaInvalida, match="no existe"):
        celda_demo().posicion_de("tablero:z9")


def test_objeto_fijo_genera_zona_prohibida():
    celda = celda_demo()
    nombres = [z["nombre"] for z in celda.zonas_efectivas]
    assert "tripode_camara" in nombres and "cilindro_azul" not in nombres


def test_campo_desconocido_se_ignora_con_aviso():
    celda = celda_desde_dict({"nombre": "x", "campo_raro": 1, "objetos": [{"nombre": "a", "forma": "caja", "tamano_mm": [10, 10, 10], "posicion": [0, 0, 0], "color": "rojo"}]})
    assert any("campo_raro" in a for a in celda.avisos) and any("color" in a for a in celda.avisos)
    assert "a" in celda.objetos


def test_objeto_invalido_falla_con_mensaje():
    with pytest.raises(CeldaInvalida, match="tamano_mm"):
        celda_desde_dict({"objetos": [{"nombre": "a", "forma": "caja", "posicion": [0, 0, 0]}]})


def test_guardar_es_atomico_y_deja_respaldo(tmp_path):
    celda = celda_demo()
    destino = tmp_path / "celda.json"
    guardar_celda(celda, destino)
    celda.nombre = "otra"
    guardar_celda(celda, destino)
    assert json.loads(destino.read_text())["nombre"] == "otra"
    assert json.loads((tmp_path / "celda.json.bak").read_text())["nombre"] == celda.nombre.replace("otra", "Celda de práctica (simulador)")
    assert not list(tmp_path.glob("*.tmp"))


def test_guardar_celda_invalida_no_toca_el_disco(tmp_path):
    celda = celda_demo()
    destino = tmp_path / "celda.json"
    guardar_celda(celda, destino)
    antes = destino.read_text()
    celda.objetos["caja_roja"].tamano_mm = (0, 0, 0)
    with pytest.raises(CeldaInvalida):
        guardar_celda(celda, destino)
    assert destino.read_text() == antes


def test_guardar_y_cargar_da_lo_mismo(tmp_path):
    guardar_celda(celda_demo(), tmp_path / "celda.json")
    import shutil

    from brazo_base.celda import CELDA_DEMO

    shutil.copytree(CELDA_DEMO.parent / "herramientas", tmp_path / "herramientas")
    otra = cargar_celda(tmp_path / "celda.json")
    assert otra.objetos["caja_roja"].posicion == (-200, -500, 0)
    assert otra.superficies["tablero"].filas == 8


def test_importar_dobotstudio_trae_todos_los_alias(tmp_path):
    archivo = tmp_path / "point.json"
    archivo.write_text(json.dumps([
        {"alias": "Descanso", "pose": [1, 2, 3, 180, 0, 0], "joint": [0, 1, 2, 3, 4, 5], "tool": 0, "user": 0},
        {"alias": "esquina_mesa", "pose": [10, 20, 30, 180, 0, 0], "tool": 0, "user": 0},
        {"alias": "", "pose": [0, 0, 0, 0, 0, 0]},
    ]))
    puntos = puntos_desde_dobotstudio(archivo)
    assert set(puntos) == {"descanso", "esquina_mesa"} and puntos["descanso"]["angulos"] == [0, 1, 2, 3, 4, 5]


def test_importar_rechaza_otra_herramienta(tmp_path):
    archivo = tmp_path / "point.json"
    archivo.write_text(json.dumps([{"alias": "a", "pose": [0] * 6, "tool": 2, "user": 0}]))
    with pytest.raises(CeldaInvalida, match="tool=2"):
        puntos_desde_dobotstudio(archivo)


def test_importar_no_pisa_lo_que_ya_hay(tmp_path):
    archivo = tmp_path / "point.json"
    archivo.write_text(json.dumps([{"alias": "descanso", "pose": [9] * 6, "tool": 0, "user": 0}, {"alias": "nuevo", "pose": [1] * 6, "tool": 0, "user": 0}]))
    celda = celda_demo()
    agregados = importar_en_celda(celda, archivo)
    assert agregados == ["nuevo"] and "angulos" in celda.puntos["descanso"]
