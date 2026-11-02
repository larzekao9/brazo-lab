"""Lo que `brazo-base` ofrece para que el ajedrez corra sobre la plataforma (fase 5): celda en memoria, errores reintentables, comprobar antes de mover y poblar el simulador."""
import json
from pathlib import Path

import pytest

from brazo_base import Brazo, NoAgarro, Objeto
from brazo_base.calibracion.ajedrez import celda_de_ajedrez, celda_desde_datos
from brazo_base.celda.archivos import celda_a_dict

DATOS = json.loads((Path(__file__).parent / "datos" / "calibracion_ajedrez_ejemplo.json").read_text())


def test_la_celda_en_memoria_es_igual_a_la_del_archivo():
    celda_dict, herramienta = celda_desde_datos(DATOS)
    celda = celda_de_ajedrez(DATOS)
    assert celda.modo_pose == "brida" and celda.herramienta_config == herramienta
    assert celda_a_dict(celda)["perfiles"] == celda_dict["perfiles"] and celda.agarre == celda_dict["agarre"]


def test_la_calibracion_incompleta_dice_que_falta():
    from brazo_base import CeldaInvalida

    with pytest.raises(CeldaInvalida, match="agarre"):
        celda_desde_datos({"angulos_cero": [0] * 6, "puntos": {}})
    sin_z = json.loads(json.dumps(DATOS))
    sin_z["agarre"]["z_tope"] = None
    with pytest.raises(CeldaInvalida, match="z_tope"):
        celda_desde_datos(sin_z)


def test_no_agarro_distingue_cerrar_en_el_aire_de_caerse():
    assert NoAgarro("en el aire").reintentable is True
    assert NoAgarro("se cayó", reintentable=False).reintentable is False


@pytest.fixture
def brazo_lab():
    celda = celda_de_ajedrez(DATOS)
    with Brazo(celda=celda, velocidad_simulacion=50) as b:
        yield b


def test_comprobar_pasos_no_mueve_nada_y_valida_todo(brazo_lab):
    antes = brazo_lab.angulos()
    brazo_lab.comprobar_pasos([("tablero_ajedrez:e2", "tablero_ajedrez:e4", "p")])
    assert brazo_lab.angulos() == antes
    from brazo_base import CeldaInvalida

    with pytest.raises(CeldaInvalida, match="No conozco el lugar"):
        brazo_lab.comprobar_pasos([("tablero_ajedrez:e2", "nada:xx", "p")])
    with pytest.raises(CeldaInvalida, match="perfil"):
        brazo_lab.comprobar_pasos([("tablero_ajedrez:e2", "tablero_ajedrez:e4", "z")])


def test_cerrar_en_el_aire_es_reintentable(brazo_lab):
    with pytest.raises(NoAgarro) as error:
        brazo_lab.ejecutar_pasos([("tablero_ajedrez:e2", "tablero_ajedrez:e4", "p")])  # el simulador no tiene ninguna pieza ahí
    assert error.value.reintentable is True


def test_poblar_el_simulador_y_el_modo(brazo_lab):
    pieza = Objeto("P_e2", "cilindro", (0, -500, 8.6), radio_mm=8.5, alto_mm=42, agarrable=True, agarre_z_mm=20)
    brazo_lab.colocar_objetos_simulados([pieza])
    assert brazo_lab.posiciones_objetos() == {"P_e2": (0, -500, 8.6)} and brazo_lab.modo() == 5


def test_poblar_el_mundo_solo_existe_en_el_simulador():
    from brazo_base import ErrorBrazo

    b = Brazo(destino="real", celda=celda_de_ajedrez(DATOS))
    with pytest.raises(ErrorBrazo, match="solo existe en el simulador"):
        b.colocar_objetos_simulados([])


def test_la_punta_simulada_de_una_casilla(brazo_lab):
    from brazo_base.seguridad.perfiles import Poses

    punta = brazo_lab.punta_simulada(Poses(brazo_lab.celda).pose("tablero_ajedrez:e2", 0, "p"))
    assert punta is not None and punta[2] == pytest.approx(DATOS["agarre"]["z_tope"] - 217 + 20, abs=1.0)  # z_tope − largo + margen del peón


def test_un_perfil_desconocido_no_cae_en_el_del_peon():
    """Sin los valores medidos de una pieza no se mueve nada: bajar con la apertura del peón podría romperla."""
    from brazo_base import CeldaInvalida
    from brazo_base.seguridad.perfiles import Poses

    celda = celda_de_ajedrez(DATOS)
    del celda.perfiles["k"]
    poses = Poses(celda)
    with pytest.raises(CeldaInvalida, match="No hay un perfil de agarre «k»"):
        poses.apertura("k")
    assert poses.apertura("defecto") == pytest.approx(0.71)
