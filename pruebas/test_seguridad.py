import pytest

from brazo_base import RecorridoProhibido, celda_demo
from brazo_base.seguridad import trayectos, validador
from brazo_base.seguridad.validador import Tramo


def test_altura_de_traslado_deja_la_base_del_objeto_sobre_el_obstaculo():
    """Corrige el error del ajedrez: la base de lo que se lleva tiene que pasar `holgura` por encima del punto más alto."""
    celda = celda_demo()
    celda.seguridad["altura_segura_mm"] = 0
    z = trayectos.altura_de_traslado(celda, alto_maximo_mm=100, agarre_sobre_base_mm=20, holgura_mm=15)
    assert z == 100 + 15 + 20
    base_del_objeto = z - 20
    assert base_del_objeto == 100 + 15


def test_altura_de_traslado_respeta_la_altura_segura():
    celda = celda_demo()
    assert trayectos.altura_de_traslado(celda, 0, 0) == celda.altura_segura_mm


def test_los_objetos_fijos_no_se_sobrevuelan():
    celda = celda_demo()
    assert trayectos.alto_maximo_de_objetos(celda) < 100


def test_tramo_por_zona_prohibida_se_rechaza():
    celda = celda_demo()
    with pytest.raises(RecorridoProhibido, match="tripode_camara"):
        validador.exigir_tramos([Tramo((-300, -300, 50), (-600, -300, 50))], celda)


def test_tramo_bajo_la_altura_minima_se_rechaza():
    with pytest.raises(RecorridoProhibido, match="altura mínima"):
        validador.exigir_tramos([Tramo((0, -500, 100), (0, -500, 1))], celda_demo())


def test_tramo_fuera_de_la_mesa_se_rechaza():
    with pytest.raises(RecorridoProhibido, match="límites de la mesa"):
        validador.exigir_tramos([Tramo((0, -500, 100), (900, -500, 100))], celda_demo())


def test_tramo_libre_pasa():
    validador.exigir_tramos([Tramo((0, -500, 100), (100, -600, 120))], celda_demo())


def test_articulaciones_fuera_de_rango_se_rechazan():
    with pytest.raises(RecorridoProhibido, match="J3"):
        validador.exigir_articulaciones(None, [0, 0, 170, 0, 0, 0], celda_demo())
