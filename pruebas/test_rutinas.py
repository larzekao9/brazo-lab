import json
import shutil
from pathlib import Path

import pytest

from brazo_base import Brazo, ErrorBrazo, RecorridoProhibido, celda_demo
from brazo_base.rutinas import ErrorRutina, Rutinas, huella

DESCANSO = [298.4786, 35.3395, -150.676, 27.4337, 90.4496, -38.7623]
CERCA = [290.0, 30.0, -140.0, 30.0, 90.0, -30.0]  # una pose cercana al descanso
LAB = Path(__file__).parent.parent / "celda" / "celda.json"


@pytest.fixture
def rutinas(tmp_path):
    return Rutinas(tmp_path / "rutinas", angulos_inicio=DESCANSO, z_tope_mm=None, largo_herramienta_m=0.217)


def paso_pose(angulos=CERCA, velocidad=20):
    return {"tipo": "articulaciones", "angulos": angulos, "velocidad": velocidad}


def test_guardar_y_leer(rutinas):
    r = rutinas.guardar("saludo", [paso_pose(), {"tipo": "pinza", "apertura": 500}, {"tipo": "esperar", "segundos": 0.5}])
    assert r["nombre"] == "saludo" and not r["validada"] and len(r["pasos"]) == 3
    assert [x["nombre"] for x in rutinas.listar()] == ["posición inicial", "saludo"]


def test_la_posicion_inicial_es_incorporada_y_no_se_toca(rutinas):
    assert rutinas.obtener("posición inicial")["validada"]
    with pytest.raises(ErrorRutina, match="incorporada"):
        rutinas.guardar("posición inicial", [paso_pose()])
    with pytest.raises(ErrorRutina, match="incorporada"):
        rutinas.borrar("posición inicial")


@pytest.mark.parametrize("paso, texto", [
    ({"tipo": "articulaciones", "angulos": [0, 0, 0]}, "6 ángulos"),
    ({"tipo": "articulaciones", "angulos": [0, 0, 170, 0, 0, 0]}, "J3"),
    ({"tipo": "pinza", "apertura": 2000}, "apertura"),
    ({"tipo": "esperar", "segundos": 99}, "espera"),
    ({"tipo": "baile"}, "tipo desconocido"),
])
def test_pasos_invalidos(rutinas, paso, texto):
    with pytest.raises(ErrorRutina, match=texto):
        rutinas.guardar("mala", [paso])


def test_nombre_invalido(rutinas):
    with pytest.raises(ErrorRutina, match="nombre"):
        rutinas.guardar("../escapar", [paso_pose()])


def test_salto_grande_entre_poses_se_rechaza(rutinas):
    with pytest.raises(ErrorRutina, match="salta"):
        rutinas.guardar("salto", [paso_pose([-40] + CERCA[1:]), paso_pose([130] + CERCA[1:])])


def test_rutinas_que_llaman_a_otras_y_ciclos(rutinas):
    rutinas.guardar("a", [paso_pose()])
    rutinas.guardar("b", [{"tipo": "rutina", "nombre": "a"}, {"tipo": "esperar", "segundos": 0.1}])
    planos, _ = rutinas.pasos_para_ejecutar("b")
    assert [p["tipo"] for p in planos] == ["articulaciones", "esperar"]
    with pytest.raises(ErrorRutina, match="sí misma"):
        rutinas.guardar("c", [{"tipo": "rutina", "nombre": "c"}])


def test_la_huella_cambia_si_cambia_un_paso(rutinas):
    rutinas.guardar("x", [paso_pose()])
    h1 = rutinas.pasos_para_ejecutar("x")[1]
    rutinas.marcar_validada("x", h1)
    assert rutinas.obtener("x")["validada"]
    rutinas.guardar("x", [paso_pose(velocidad=30)])  # guardar de nuevo la deja sin validar
    assert not rutinas.obtener("x")["validada"] and rutinas.pasos_para_ejecutar("x")[1] != h1


def test_las_rutinas_reales_del_ajedrez_se_cargan(tmp_path):
    shutil.copytree(Path(__file__).parent.parent / "celda" / "rutinas", tmp_path / "r")
    nombres = [x["nombre"] for x in Rutinas(tmp_path / "r", DESCANSO).listar()]
    assert "girar" in nombres and "xcxvcx" in nombres


def test_borrar(rutinas):
    rutinas.guardar("temporal", [paso_pose()])
    rutinas.borrar("temporal")
    with pytest.raises(ErrorRutina, match="No existe"):
        rutinas.obtener("temporal")


# --- ejecución ------------------------------------------------------------------------------------------------------------
@pytest.fixture
def brazo_lab(tmp_path):
    shutil.copytree(Path(__file__).parent.parent / "celda" / "rutinas", tmp_path / "r")
    with Brazo(celda=LAB, velocidad_simulacion=25, rutinas_dir=tmp_path / "r") as b:
        yield b


def test_en_el_simulador_corre_y_queda_validada(brazo_lab):
    avances = []
    assert not brazo_lab.rutinas.obtener("xcxvcx")["validada"]
    brazo_lab.ejecutar_rutina("xcxvcx", avance=lambda i, n, t: avances.append((i, n)))
    assert avances == [(1, 1)] and brazo_lab.rutinas.obtener("xcxvcx")["validada"]


def test_primera_pose_muy_lejos_no_se_mueve(brazo_lab):
    antes = brazo_lab.angulos()
    with pytest.raises(ErrorBrazo, match="a 298°"):
        brazo_lab.ejecutar_rutina("girar")
    assert brazo_lab.angulos() == antes


def test_factor_fuera_de_rango(brazo_lab):
    with pytest.raises(ErrorBrazo, match="factor"):
        brazo_lab.ejecutar_rutina("xcxvcx", factor=5)


def test_una_rutina_con_zona_prohibida_no_mueve_nada(brazo_lab):
    brazo_lab.celda.zonas_prohibidas.append({"nombre": "todo", "forma": "rectangulo", "x1": -2000, "y1": -2000, "x2": 2000, "y2": 2000})
    antes = brazo_lab.angulos()
    with pytest.raises(RecorridoProhibido):
        brazo_lab.ejecutar_rutina("xcxvcx")
    assert brazo_lab.angulos() == antes


class ClienteFalso:
    velocidad_global, cancelado = 50, False

    def __init__(self):
        self.log = []

    def reanudar(self):
        pass

    def angulos(self):
        return tuple(DESCANSO)

    def enviar(self, comando):
        self.log.append(comando)

    def mover_a_angulos(self, angulos, **kw):
        self.log.append(("angulos", tuple(angulos)))


class HerramientaFalsa:
    largo_mm = 217.0

    def estado(self):
        return {"inicializada": True}


def real_falso(tmp_path, validada):
    celda = celda_demo()
    celda.puntos["descanso"] = {"angulos": DESCANSO}
    b = Brazo(destino="real", celda=celda, rutinas_dir=tmp_path)
    b._cliente, b._habilitado, b.herramienta = ClienteFalso(), True, HerramientaFalsa()
    b.celda.zonas_prohibidas.clear()
    b.celda.objetos.clear()
    b.celda.seguridad["limites_mesa"] = None
    r = b.rutinas
    r.guardar("va", [paso_pose([CERCA[0], *CERCA[1:]], velocidad=80)])
    if validada:
        r.marcar_validada("va", r.pasos_para_ejecutar("va")[1])
    return b


def test_el_brazo_real_exige_validacion_previa(tmp_path):
    b = real_falso(tmp_path, validada=False)
    with pytest.raises(ErrorBrazo, match="todavía no corrió completa en el simulador"):
        b.ejecutar_rutina("va", confirmar=True)
    assert b._cliente.log == []


def test_el_brazo_real_exige_confirmacion(tmp_path):
    b = real_falso(tmp_path, validada=True)
    with pytest.raises(ErrorBrazo, match="Confirmá"):
        b.ejecutar_rutina("va")
    assert b._cliente.log == []


def test_el_brazo_real_respeta_el_tope_de_velocidad(tmp_path):
    b = real_falso(tmp_path, validada=True)
    b.ejecutar_rutina("va", confirmar=True, factor=2)
    log = b._cliente.log
    assert "SpeedFactor(50)" in log  # 80 % x 2 pedido, pero la celda topa el real en 50 %
    assert log[-1] == "SpeedFactor(50)"  # y al terminar vuelve a la velocidad que tenía
