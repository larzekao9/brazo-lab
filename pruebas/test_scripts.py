"""La consola de scripts: el script corre en un proceso aparte y habla con un servidor HTTP REAL (por eso estas pruebas arrancan uno)."""
import threading
import time

import httpx
import pytest
import uvicorn

from brazo_base.scripts.ejecutor import EjecutorScripts, ErrorScript, Validados, huella_de
from brazo_base.servidor.api import crear_app
from brazo_base.servidor.servicio import ServicioBrazo


@pytest.fixture
def servidor(tmp_path):
    servicio = ServicioBrazo(datos_dir=tmp_path)
    server = uvicorn.Server(uvicorn.Config(crear_app(servicio), host="127.0.0.1", port=0, log_level="warning"))
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    while not server.started:
        time.sleep(0.05)
    puerto = server.servers[0].sockets[0].getsockname()[1]
    with httpx.Client(base_url=f"http://127.0.0.1:{puerto}", timeout=30) as cliente:
        yield cliente, servicio
    servicio.scripts.parar()
    servicio.desconectar()
    server.should_exit = True
    hilo.join(10)


def conectar(cliente):
    assert cliente.post("/conectar", json={"velocidad_simulacion": 25}).status_code == 200
    assert cliente.post("/habilitar").status_code == 200


def correr(cliente, codigo, **extra):
    r = cliente.post("/scripts/ejecutar", json={"codigo": codigo, **extra})
    assert r.status_code == 202, r.text
    return esperar(cliente)


def esperar(cliente, limite=60):
    fin = time.time() + limite
    while time.time() < fin:
        e = cliente.get("/scripts/estado").json()
        if e["estado"] != "corriendo":
            return e
        time.sleep(0.2)
    raise AssertionError("el script no terminó")


def test_un_script_mueve_el_brazo_y_queda_validado(servidor):
    cliente, _ = servidor
    conectar(cliente)
    antes = cliente.get("/estado").json()["pose"][2]
    e = correr(cliente, 'brazo.mover_relativo(dz=10)\nprint("z =", round(brazo.pose()[2], 1))\nprint("sostiene:", brazo.herramienta.cerrar())')
    assert e["estado"] == "terminado" and e["codigo_salida"] == 0, e["salida"]
    assert f"z = {round(antes + 10, 1)}" in e["salida"][0] and "sostiene: False" in e["salida"][1]
    assert cliente.get("/estado").json()["pose"][2] == pytest.approx(antes + 10, abs=0.2)  # el brazo del servidor se movió de verdad
    assert e["validado_para_real"] is True


def test_un_script_que_falla_muestra_el_error_y_no_queda_validado(servidor):
    cliente, _ = servidor
    conectar(cliente)
    e = correr(cliente, 'print("antes")\nraise ValueError("se rompió")')
    assert e["estado"] == "error" and e["codigo_salida"] != 0
    assert e["salida"][0] == "antes" and any("ValueError: se rompió" in linea for linea in e["salida"])
    assert e["validado_para_real"] is False


def test_un_recorrido_prohibido_dentro_del_script_se_rechaza(servidor):
    cliente, _ = servidor
    conectar(cliente)
    e = correr(cliente, "brazo.mover_a(-450, -300, 50)")
    assert e["estado"] == "error" and any("tripode_camara" in linea for linea in e["salida"])


def test_el_script_ve_la_celda_y_los_objetos(servidor):
    cliente, _ = servidor
    conectar(cliente)
    e = correr(cliente, 'brazo.llevar("caja_roja", "bandeja")\nprint("listo")')
    assert e["estado"] == "terminado" and e["salida"][-1] == "listo"
    assert [round(v) for v in cliente.get("/estado").json()["objetos"]["caja_roja"]] == [250, -500, 0]


@pytest.mark.parametrize("codigo, codigo_http, texto", [("", 422, "vacío"), ("def f(:\n  pass", 422, "sintaxis"), ("x = " + "1" * 21000, 422, "")])
def test_codigo_invalido(servidor, codigo, codigo_http, texto):
    cliente, _ = servidor
    conectar(cliente)
    r = cliente.post("/scripts/ejecutar", json={"codigo": codigo})
    assert r.status_code == codigo_http and texto in r.text


def test_sin_conexion_no_corre(servidor):
    cliente, _ = servidor
    r = cliente.post("/scripts/ejecutar", json={"codigo": "print(1)"})
    assert r.status_code == 409 and "conectar" in r.json()["error"]


def test_sin_habilitar_no_corre(servidor):
    cliente, _ = servidor
    cliente.post("/conectar", json={"velocidad_simulacion": 25})
    r = cliente.post("/scripts/ejecutar", json={"codigo": "print(1)"})
    assert r.status_code == 409 and "habilit" in r.json()["error"]


def test_el_tiempo_limite_corta_el_script(servidor):
    cliente, _ = servidor
    conectar(cliente)
    e = correr(cliente, "import time\nprint('arranca', flush=True)\ntime.sleep(60)", limite_segundos=2)
    assert e["estado"] == "tiempo" and "tiempo límite" in e["salida"][-1] and e["duracion_s"] < 10


def test_parar_corta_el_script_y_frena_el_brazo(servidor):
    cliente, servicio = servidor
    conectar(cliente)
    assert cliente.post("/scripts/ejecutar", json={"codigo": "while True:\n    brazo.mover_relativo(dz=5)\n    brazo.mover_relativo(dz=-5)"}).status_code == 202
    time.sleep(2.0)
    assert cliente.post("/scripts/parar").status_code == 200
    e = esperar(cliente, 15)
    assert e["estado"] == "cancelado"
    time.sleep(1.0)
    assert servicio.estado()["tarea"]["estado"] != "en_curso"  # la tarea que estaba moviendo el brazo también se cortó


def test_dos_scripts_a_la_vez_no(servidor):
    cliente, _ = servidor
    conectar(cliente)
    assert cliente.post("/scripts/ejecutar", json={"codigo": "import time\ntime.sleep(5)"}).status_code == 202
    r = cliente.post("/scripts/ejecutar", json={"codigo": "print(1)"})
    assert r.status_code == 409 and "Ya hay un script" in r.json()["error"]
    cliente.post("/scripts/parar")
    esperar(cliente, 15)


def test_la_salida_larga_se_corta(servidor):
    cliente, _ = servidor
    conectar(cliente)
    e = correr(cliente, "for i in range(5000):\n    print(i)")
    assert e["estado"] == "terminado" and e["total"] <= 2001 and "salida cortada" in e["salida"][-1]


def test_la_huella_ignora_fines_de_linea_y_espacios_al_final():
    assert huella_de("a = 1\nb = 2\n") == huella_de("a = 1  \r\nb = 2\r\n\r\n") != huella_de("a = 1\nb = 3")


def test_huella_por_http(servidor):
    cliente, _ = servidor
    r = cliente.post("/scripts/huella", json={"codigo": "print(1)"}).json()
    assert r["huella"] == huella_de("print(1)") and r["validado_para_real"] is False


# --- la regla del brazo real (sin conectar nada: es del ejecutor) ------------------------------------------------------------------------
def test_para_el_brazo_real_el_script_tiene_que_haber_corrido_en_el_simulador(tmp_path):
    ejecutor = EjecutorScripts(Validados(tmp_path / "v.json"))
    with pytest.raises(ErrorScript, match="todavía no terminó sin errores en el simulador") as error:
        ejecutor.iniciar("print('hola')", "http://127.0.0.1:1", "real", confirmar=True)
    assert error.value.codigo == 409


def test_para_el_brazo_real_hace_falta_confirmar(tmp_path):
    ejecutor = EjecutorScripts(Validados(tmp_path / "v.json"))
    ejecutor.validados.marcar(huella_de("print('hola')"))
    with pytest.raises(ErrorScript, match="Confirmá"):
        ejecutor.iniciar("print('hola')", "http://127.0.0.1:1", "real")


def test_validado_y_confirmado_corre_pero_no_se_valida_otro_codigo(tmp_path):
    ejecutor = EjecutorScripts(Validados(tmp_path / "v.json"))
    ejecutor.validados.marcar(huella_de("print('hola')"))
    ejecutor.iniciar("print('hola')", "http://127.0.0.1:1", "real", confirmar=True)
    for _ in range(100):
        if not ejecutor.corriendo():
            break
        time.sleep(0.1)
    e = ejecutor.leer()
    assert e["estado"] == "terminado" and e["salida"] == ["hola"]
    # un código distinto, aunque sea parecido, no está validado
    with pytest.raises(ErrorScript):
        ejecutor.iniciar("print('hola!')", "http://127.0.0.1:1", "real", confirmar=True)


def test_correr_en_el_real_no_valida_el_codigo(tmp_path):
    ejecutor = EjecutorScripts(Validados(tmp_path / "v.json"))
    ejecutor.validados.marcar(huella_de("pass"))
    ejecutor.iniciar("pass", "http://127.0.0.1:1", "real", confirmar=True)
    while ejecutor.corriendo():
        time.sleep(0.1)
    ejecutor.iniciar("x = 1", "http://127.0.0.1:1", "simulador")
    while ejecutor.corriendo():
        time.sleep(0.1)
    assert ejecutor.validados.esta(huella_de("x = 1")) and not ejecutor.validados.esta(huella_de("y = 1"))
