import threading
import time

import pytest

from brazo_base import Brazo, ErrorBrazo, NoAgarro, NoHabilitado, RecorridoProhibido, SinConexion


def test_destino_real_exige_celda():
    with pytest.raises(ErrorBrazo, match="celda del laboratorio"):
        Brazo(destino="real")


def test_destino_invalido():
    with pytest.raises(ErrorBrazo, match="simulador"):
        Brazo(destino="otro")


def test_sin_conectar_dice_que_hacer():
    with pytest.raises(SinConexion, match="conectar"):
        Brazo().pose()


def test_conectado_sin_habilitar_no_mueve():
    b = Brazo(velocidad_simulacion=25)
    b.conectar()
    try:
        with pytest.raises(NoHabilitado, match="habilitar"):
            b.mover_a(0, -400, 200)
    finally:
        b.desconectar()


def test_la_pose_esta_en_el_tcp(brazo):
    brazo.mover_a(0, -500, 100)
    x, y, z, rx, *_ = brazo.pose()
    assert (round(x), round(y), round(z)) == (0, -500, 100)
    assert abs(rx) == pytest.approx(180, abs=0.01)
    # el controlador (la brida) está 217 mm más arriba
    assert round(brazo._cliente.pose()[2]) == 100 + 217


def test_mover_relativo(brazo):
    brazo.mover_a(0, -500, 100)
    brazo.mover_relativo(dz=20, dx=10)
    x, y, z, *_ = brazo.pose()
    assert (round(x), round(y), round(z)) == (10, -500, 120)


def test_girar_la_muneca_no_corre_la_punta(brazo):
    brazo.mover_a(0, -500, 100, rz=0)
    brazo.mover_a(rz=60)
    x, y, z, *_ = brazo.pose()
    assert (round(x, 1), round(y, 1), round(z, 1)) == (0, -500, 100)


def test_zona_prohibida_falla_antes_de_mover(brazo):
    brazo.mover_a(-300, -300, 100)
    antes = brazo.pose()
    with pytest.raises(RecorridoProhibido, match="tripode_camara"):
        brazo.mover_a(-600, -300, 100)
    assert brazo.pose() == antes


def test_punto_ir_a_descanso(brazo):
    inicial = brazo.pose()
    brazo.mover_a(0, -500, 100)
    brazo.ir_a("descanso")
    assert brazo.pose() == pytest.approx(inicial, abs=0.2)


def test_llevar_una_caja_de_un_lugar_a_otro(brazo):
    brazo.llevar("caja_roja", "bandeja")
    x, y, z = brazo.simulador.telemetria()["objetos"]["caja_roja"]
    assert (round(x), round(y), round(z)) == (250, -500, 0)
    assert brazo.estado()["sostiene"] is None


def test_llevar_apila_sobre_otro_objeto(brazo):
    brazo.llevar("caja_roja", "bandeja")
    brazo.llevar("cilindro_azul", "caja_roja")
    _, _, z = brazo.simulador.telemetria()["objetos"]["cilindro_azul"]
    assert round(z) == 40  # el tope de la caja


def test_agarrar_y_soltar_por_separado(brazo):
    brazo.agarrar("caja_roja")
    assert brazo.estado()["sostiene"] == "caja_roja"
    assert brazo.simulador.telemetria()["sostiene"] == "caja_roja"
    brazo.soltar_en("tablero:c3")
    assert brazo.simulador.telemetria()["sostiene"] is None


def test_soltar_sin_agarrar(brazo):
    with pytest.raises(NoAgarro, match="agarrar"):
        brazo.soltar_en("bandeja")


def test_agarrar_dos_veces(brazo):
    brazo.agarrar("caja_roja")
    with pytest.raises(NoAgarro, match="Ya estás sosteniendo"):
        brazo.agarrar("cilindro_azul")


def test_agarrar_un_objeto_fijo(brazo):
    with pytest.raises(ErrorBrazo, match="no es agarrable"):
        brazo.agarrar("tripode_camara")


def test_agarrar_en_el_vacio_da_no_agarro(brazo):
    brazo._posiciones["caja_roja"] = (100, -450, 0)  # la celda cree que está acá y en el simulador no
    with pytest.raises(NoAgarro, match="no sostiene nada"):
        brazo.agarrar("caja_roja")


def test_objeto_que_no_cabe_en_la_pinza(brazo):
    brazo.celda.objetos["caja_roja"].tamano_mm = (40, 40, 40)
    with pytest.raises(ErrorBrazo, match="no cabe"):
        brazo.agarrar("caja_roja")


def test_pieza_que_se_cae_se_detecta(brazo):
    brazo.agarrar("caja_roja")
    brazo.simulador.provocar("pieza_cae")
    time.sleep(0.4)
    assert brazo.herramienta.estado()["sostiene"] is False


def test_llevar_con_destino_prohibido_no_mueve_nada(brazo):
    brazo.celda.lugares["trampa"] = {"x": -450, "y": -300, "z": 0}
    antes = brazo.pose()
    with pytest.raises(RecorridoProhibido):
        brazo.llevar("caja_roja", "trampa")
    assert brazo.pose() == antes
    assert brazo.estado()["sostiene"] is None


def test_parar_corta_el_movimiento_en_curso():
    with Brazo(velocidad_simulacion=1, velocidad=10) as b:
        errores = []

        def mover():
            try:
                b.mover_a(0, -600, 100)
            except ErrorBrazo as e:
                errores.append(e)

        hilo = threading.Thread(target=mover)
        hilo.start()
        time.sleep(0.6)
        b.parar()
        hilo.join(5)
        assert not hilo.is_alive()
        x, y, z, *_ = b.pose()
        assert y > -600 + 5  # no llegó
        b.mover_relativo(dz=5)  # el siguiente movimiento anda (corto: a esta velocidad uno largo tarda mucho)
