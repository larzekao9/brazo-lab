"""El pick and place por perfiles manda EXACTAMENTE lo que mandaba el `EjecutorReal` del ajedrez con el brazo real (calibración del 2026-11-02).

`datos/golden_ejecutor_real_ajedrez.json` se generó ejecutando `EjecutorReal` del ajedrez con clientes falsos; acá se repite con `Brazo.ejecutar_pasos` y se comparan
los comandos uno por uno (pose, recta o articular, velocidad y aceleración, y posición de la pinza).
"""
import json
from pathlib import Path

import pytest

from brazo_base import Brazo, NoAgarro
from brazo_base.celda import cargar_celda

DATOS = Path(__file__).parent / "datos"
ORO = json.loads((DATOS / "golden_ejecutor_real_ajedrez.json").read_text())


def r(p):
    return [round(float(v), 4) for v in p]


class Cliente:
    velocidad, aceleracion, cancelado = 50, 15, False

    def __init__(self, log):
        self.log = log

    def mover_a_pose(self, pose, lineal=False, aceleracion=None, velocidad=None):
        self.log.append(["pose", r(pose), bool(lineal), aceleracion, velocidad])

    def mover_a_angulos(self, angulos, **kw):
        self.log.append(["angulos", r(angulos)])

    def pose(self):
        return (-34.2, 318.8, 350.6, -88.1, -1.0, 67.2)

    def reanudar(self):
        pass


class Herramienta:
    largo_mm = 217.0

    def __init__(self, log, sostiene=True):
        self.log, self.sostiene = log, sostiene

    def abrir_a(self, f):
        self.log.append(["pinza", round(f * 1000)])

    def cerrar(self):
        self.log.append(["pinza", 0])
        return self.sostiene

    def estado(self):
        return {"inicializada": True, "sostiene": self.sostiene}


def brazo_con(log, sostiene=True):
    b = Brazo(destino="real", celda=cargar_celda(DATOS / "celda_ajedrez" / "celda.json"))
    b._cliente, b._habilitado, b.herramienta = Cliente(log), True, Herramienta(log, sostiene)
    return b


def lugar(nombre):
    return nombre if ":" in nombre else f"tablero_ajedrez:{nombre}"


@pytest.mark.parametrize("clave", list(ORO))
def test_misma_secuencia_que_el_ajedrez(clave):
    desde, hasta, perfil = clave.split(">")
    log = []
    brazo_con(log).ejecutar_pasos([(lugar(desde), lugar(hasta), perfil)])
    assert log == json.loads(json.dumps(ORO[clave]))


def test_sin_agarrar_nada_se_retira_y_avisa():
    log = []
    with pytest.raises(NoAgarro, match="no sintió nada"):
        brazo_con(log, sostiene=False).ejecutar_pasos([("tablero_ajedrez:e2", "tablero_ajedrez:e4", "p")])
    assert log[-1][0] == "pose" and log[-1][2] is True  # sube despacio y no sigue con el paso


def test_perfil_sin_apertura_falla_antes_de_mover():
    celda = cargar_celda(DATOS / "celda_ajedrez" / "celda.json")
    del celda.perfiles["n"]["apertura"]
    log = []
    b = Brazo(destino="real", celda=celda)
    b._cliente, b._habilitado, b.herramienta = Cliente(log), True, Herramienta(log)
    with pytest.raises(Exception, match="apertura"):
        b.ejecutar_pasos([("tablero_ajedrez:g1", "tablero_ajedrez:f3", "n")])
    assert log == []
