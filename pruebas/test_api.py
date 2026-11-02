import json
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from brazo_base.celda import CELDA_DEMO
from brazo_base.servidor.api import crear_app
from brazo_base.servidor.servicio import ServicioBrazo


@pytest.fixture
def cliente():
    servicio = ServicioBrazo()
    with TestClient(crear_app(servicio)) as c:
        yield c
    servicio.desconectar()


def conectado(c):
    assert c.post("/conectar", json={"velocidad_simulacion": 25}).status_code == 200
    assert c.post("/habilitar").status_code == 200


def esperar_tarea(c, limite=60):
    fin = time.time() + limite
    while time.time() < fin:
        t = c.get("/estado").json()["tarea"]
        if t["estado"] != "en_curso":
            return t
        time.sleep(0.1)
    raise AssertionError("la tarea no terminó")


def test_estado_sin_conexion(cliente):
    assert cliente.get("/estado").json()["conectado"] is False


def test_mover_sin_conexion_da_409_con_mensaje(cliente):
    r = cliente.post("/mover", json={"x": 0, "y": -400, "z": 100})
    assert r.status_code == 409 and "conectar" in r.json()["error"]


def test_real_pide_confirmacion(cliente):
    r = cliente.post("/conectar", json={"destino": "real", "celda": "celda/celda.json"})
    assert r.status_code == 409 and "confirmar_real" in r.json()["error"]


def test_mover_responde_202_y_la_tarea_termina(cliente):
    conectado(cliente)
    r = cliente.post("/mover", json={"x": 0, "y": -500, "z": 120})
    assert r.status_code == 202 and r.json()["estado"] == "en_curso"
    assert esperar_tarea(cliente)["estado"] == "terminada"
    x, y, z, *_ = cliente.get("/estado").json()["pose"]
    assert (round(x), round(y), round(z)) == (0, -500, 120)


def test_recorrido_prohibido_es_422_y_no_mueve(cliente):
    conectado(cliente)
    antes = cliente.get("/estado").json()["pose"]
    r = cliente.post("/mover", json={"x": -450, "y": -300, "z": 50})
    assert r.status_code == 422 and "tripode_camara" in r.json()["problemas"][0]
    assert cliente.get("/estado").json()["pose"] == antes


def test_mover_sin_datos_es_422(cliente):
    conectado(cliente)
    assert cliente.post("/mover", json={}).status_code == 422


def test_llevar_y_ensayo(cliente):
    conectado(cliente)
    ens = cliente.post("/ensayo", json={"tipo": "llevar", "desde": "caja_roja", "hasta": "bandeja"}).json()
    assert ens["ok"] and ens["tramos"]
    assert cliente.post("/llevar", json={"desde": "caja_roja", "hasta": "bandeja"}).status_code == 202
    assert esperar_tarea(cliente)["estado"] == "terminada"
    assert [round(v) for v in cliente.get("/estado").json()["objetos"]["caja_roja"]] == [250, -500, 0]


def test_dos_tareas_a_la_vez_es_409(cliente):
    conectado(cliente)
    assert cliente.post("/llevar", json={"desde": "caja_roja", "hasta": "bandeja"}).status_code == 202
    r = cliente.post("/mover", json={"x": 0, "y": -450, "z": 150})
    assert r.status_code == 409 and "en curso" in r.json()["error"]
    esperar_tarea(cliente)


def test_parar_corta_la_tarea():
    servicio = ServicioBrazo()
    with TestClient(crear_app(servicio)) as c:
        assert c.post("/conectar", json={"velocidad_simulacion": 1, "velocidad": 10}).status_code == 200
        c.post("/habilitar")
        c.post("/mover", json={"x": 0, "y": -650, "z": 100})
        time.sleep(0.6)
        assert c.post("/parar").status_code == 200
        assert esperar_tarea(c, 10)["estado"] == "cancelada"
        assert c.get("/estado").json()["pose"][1] > -645
        assert c.post("/mover", json={"dz": 5}).status_code == 202  # vuelve a andar (corto: a esta velocidad uno largo tarda mucho)
        assert esperar_tarea(c, 30)["estado"] == "terminada"
    servicio.desconectar()


def test_herramienta(cliente):
    conectado(cliente)
    assert cliente.post("/herramienta", json={"accion": "cerrar"}).status_code == 202
    assert esperar_tarea(cliente)["resultado"] == {"sostiene": False}
    assert cliente.post("/herramienta", json={"accion": "abrir_a", "valor": 5}).status_code == 422


def test_fallo_alarma_y_limpiar(cliente):
    conectado(cliente)
    assert cliente.post("/simulador/fallo", json={"fallo": "alarma"}).status_code == 200
    assert cliente.get("/estado").json()["modo"] == 9
    assert cliente.post("/limpiar-error").status_code == 200
    assert cliente.get("/estado").json()["modo"] == 5


def test_punto_con_nombre_en_memoria(cliente):
    conectado(cliente)
    assert cliente.put("/puntos/mi_punto", json={}).status_code == 200
    assert "mi_punto" in cliente.get("/celda").json()["puntos"]
    assert cliente.put("/puntos/mi punto", json={}).status_code == 422
    assert cliente.put("/puntos/otro", json={"guardar": True}).status_code == 409  # la celda demo no se escribe


def test_celda_se_valida_y_guarda(cliente, tmp_path):
    shutil.copytree(CELDA_DEMO.parent / "herramientas", tmp_path / "herramientas")
    datos = json.loads(CELDA_DEMO.read_text())
    ruta = str(tmp_path / "celda.json")
    assert cliente.put("/celda", json={"ruta": ruta, "celda": datos}).status_code == 200
    datos["objetos"][0]["tamano_mm"] = [0, 0, 0]
    r = cliente.put("/celda", json={"ruta": ruta, "celda": datos})
    assert r.status_code == 422 and "tamano_mm" in r.json()["error"]


def test_telemetria_por_websocket(cliente):
    conectado(cliente)
    with cliente.websocket_connect("/telemetria") as ws:
        e = ws.receive_json()
    assert e["conectado"] and len(e["brazo_puntos"]) >= 6 and "caja_roja" in e["objetos"]


def test_cors_solo_para_origenes_locales(cliente):
    local = cliente.options("/estado", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    ajeno = cliente.options("/estado", headers={"Origin": "https://pagina-ajena.com", "Access-Control-Request-Method": "GET"})
    assert local.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in ajeno.headers


def test_el_panel_se_sirve(cliente):
    assert "brazo-base" in cliente.get("/").text
    assert cliente.get("/panel/panel.js").status_code == 200


def test_mover_relativo_conserva_la_orientacion(cliente):
    conectado(cliente)
    antes = cliente.get("/estado").json()["pose"]
    assert cliente.post("/mover", json={"dz": 10}).status_code == 202
    assert esperar_tarea(cliente)["estado"] == "terminada"
    despues = cliente.get("/estado").json()["pose"]
    assert despues[2] == pytest.approx(antes[2] + 10, abs=0.2) and despues[3:] == pytest.approx(antes[3:], abs=0.2)
