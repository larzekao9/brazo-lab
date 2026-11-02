import json
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from brazo_base.celda import CELDA_DEMO
from brazo_base.servidor.api import crear_app
from brazo_base.servidor.servicio import ServicioBrazo


@pytest.fixture
def cliente(tmp_path):
    servicio = ServicioBrazo(datos_dir=tmp_path)  # las rutinas y los scripts validados se guardan en una carpeta de prueba, no en ~/.brazo-base
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


def test_parar_corta_la_tarea(tmp_path):
    servicio = ServicioBrazo(datos_dir=tmp_path)
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
    nulo = cliente.options("/estado", headers={"Origin": "null", "Access-Control-Request-Method": "GET"})
    assert local.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in ajeno.headers and "access-control-allow-origin" not in nulo.headers


@pytest.mark.parametrize("origen", ["https://pagina-ajena.com", "null", "http://localhost.evil.com", "http://127.0.0.1.evil.com:8000"])
def test_un_pedido_que_cambia_algo_desde_una_pagina_ajena_se_rechaza(cliente, origen):
    """Aunque el navegador no haga preflight (pedido «simple»), el servidor no mueve ni ejecuta nada si el origen no es de este equipo."""
    r = cliente.post("/conectar", json={}, headers={"Origin": origen})
    assert r.status_code == 403 and "no es de este equipo" in r.json()["error"]
    assert cliente.get("/estado").json()["conectado"] is False


def test_un_pedido_desde_localhost_pasa(cliente):
    assert cliente.post("/conectar", json={"velocidad_simulacion": 25}, headers={"Origin": "http://127.0.0.1:8000"}).status_code == 200


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


# --- fase 3: rutinas, calibración y más pick and place -----------------------------------------------------------------------------------
CERCA = [298.0, 35.0, -150.0, 27.0, 90.0, -39.0]  # casi el descanso: una pose válida y cercana


def test_rutinas_por_http(cliente):
    conectado(cliente)
    assert [r["nombre"] for r in cliente.get("/rutinas").json()] == ["posición inicial"]
    assert cliente.put("/rutinas/ida", json={"pasos": [{"tipo": "articulaciones", "angulos": CERCA, "velocidad": 50}, {"tipo": "pinza", "apertura": 500}]}).status_code == 200
    r = cliente.get("/rutinas/ida").json()
    assert r["validada"] is False
    assert cliente.post("/rutinas/ida/ejecutar", json={}).status_code == 202
    assert esperar_tarea(cliente)["estado"] == "terminada"
    assert cliente.get("/rutinas/ida").json()["validada"] is True  # corrió completa en el simulador
    assert cliente.delete("/rutinas/ida").status_code == 200
    assert cliente.get("/rutinas/ida").status_code == 404


def test_rutina_invalida_es_422_con_mensaje(cliente):
    conectado(cliente)
    r = cliente.put("/rutinas/mala", json={"pasos": [{"tipo": "articulaciones", "angulos": [0, 0, 170, 0, 0, 0]}]})
    assert r.status_code == 422 and "J3" in r.json()["error"]
    assert cliente.put("/rutinas/posición inicial", json={"pasos": [{"tipo": "esperar", "segundos": 1}]}).status_code == 409


def test_rutina_con_la_primera_pose_lejos_se_rechaza_antes_de_mover(cliente):
    conectado(cliente)
    cliente.put("/rutinas/lejos", json={"pasos": [{"tipo": "articulaciones", "angulos": [0, 0, 90, 0, 90, 0]}]})
    antes = cliente.get("/estado").json()["angulos"]
    r = cliente.post("/rutinas/lejos/ejecutar", json={})
    assert r.status_code in (409, 422) and ("primera pose" in r.json()["error"] or "no se movió nada" in r.json()["error"])
    assert cliente.get("/estado").json()["angulos"] == antes  # rechazada antes de mandar el primer comando


def test_agarrar_y_soltar_por_http(cliente):
    conectado(cliente)
    assert cliente.post("/agarrar", json={"objeto": "caja_roja"}).status_code == 202
    assert esperar_tarea(cliente)["estado"] == "terminada" and cliente.get("/estado").json()["sostiene"] == "caja_roja"
    assert cliente.post("/soltar", json={"lugar": "bandeja"}).status_code == 202
    assert esperar_tarea(cliente)["estado"] == "terminada"


def test_llevar_desde_con_la_celda_del_laboratorio_sin_pieza_avisa(cliente):
    from pathlib import Path

    lab = str(Path(__file__).parent.parent / "celda" / "celda.json")
    assert cliente.post("/conectar", json={"celda": lab, "velocidad_simulacion": 25}).status_code == 200
    cliente.post("/habilitar")
    assert cliente.post("/llevar-desde", json={"desde": "tablero_ajedrez:e2", "hasta": "tablero_ajedrez:e4", "perfil": "p"}).status_code == 202
    t = esperar_tarea(cliente)
    assert t["estado"] == "error" and "no sintió nada" in t["error"]  # en el simulador no hay una pieza en e2


def test_calibrar_una_superficie(cliente):
    conectado(cliente)
    puntos = {"a1": [-120.25, -674.2, 225.0, 177.8, -2.4, -82.1], "h1": [171.8, -679.7, 224.2, 177.8, -2.1, -58.0], "a8": [-119.7, -372.7, 221.5, 179.5, -3.3, -80.6]}
    r = cliente.post("/calibracion/superficie", json={"nombre": "mesa_nueva", "puntos": puntos, "filas": 8, "columnas": 8})
    assert r.status_code == 200 and r.json()["z_mm"] == 225.0 and "mesa_nueva" in cliente.get("/celda").json()["superficies"]
    malo = cliente.post("/calibracion/superficie", json={"nombre": "x", "puntos": {"a1": [0, 0, 0]}, "filas": 8, "columnas": 8})
    assert malo.status_code == 422 and "esquinas" in malo.json()["error"]
    assert cliente.post("/calibracion/superficie", json={"nombre": "mesa_nueva", "puntos": puntos, "filas": 8, "columnas": 8, "guardar": True}).status_code == 409  # la celda demo no se escribe


def test_largo_de_la_herramienta(cliente):
    assert cliente.post("/calibracion/largo-herramienta", json={"z_brida_mm": 225.6, "z_superficie_mm": 8.6}).json()["largo_mm"] == pytest.approx(217.0)
    assert cliente.post("/calibracion/largo-herramienta", json={}).status_code == 422
    assert cliente.post("/calibracion/largo-herramienta", json={"z_brida_mm": 5, "z_superficie_mm": 20}).status_code == 422


def test_guardar_un_lugar_llevando_el_brazo(cliente):
    conectado(cliente)
    cliente.post("/mover", json={"x": 100, "y": -450, "z": 80})
    esperar_tarea(cliente)
    r = cliente.put("/lugares/mi_lugar", json={})
    assert r.status_code == 200 and (r.json()["x"], r.json()["y"]) == pytest.approx((100, -450), abs=0.2)
    assert cliente.put("/lugares/otro", json={"guardar": True}).status_code == 409
