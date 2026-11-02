import random
from pathlib import Path

import numpy as np
import pytest

from brazo_base import Brazo, CeldaInvalida
from brazo_base.calibracion.herramienta import calibrar_por_pivote, largo_por_apoyo
from brazo_base.calibracion.superficie import calibrar_superficie
from brazo_base.celda import cargar_celda
from brazo_base.simulador.cinematica import rotacion_de_euler

DATOS = Path(__file__).parent / "datos"
# las 4 esquinas REALES enseñadas en el laboratorio (calibracion_local/brazo.json del ajedrez)
A1 = (-120.2501, -674.2083, 225.0079, 177.7786, -2.3812, -82.0584)
H1 = (171.7961, -679.6634, 224.2345, 177.7839, -2.1144, -58.049)
A8 = (-119.6829, -372.7432, 221.5248, 179.4505, -3.2605, -80.6175)
H8 = (177.0482, -382.7433, 221.3982, 178.976, -2.1128, -66.924)


def test_la_superficie_de_las_esquinas_reales_da_las_mismas_casillas_que_el_ajedrez():
    superficie, avisos = calibrar_superficie("tablero", {"a1": A1, "h1": H1, "a8": A8, "h8": H8}, 8, 8, z_mm=225.6)
    lab = cargar_celda(DATOS / "celda_ajedrez" / "celda.json").superficies["tablero_ajedrez"]
    for casilla in ("a1", "e4", "h8", "d6"):
        esperado = lab.lugar(casilla)
        obtenido = superficie.lugar(casilla)
        # la celda del laboratorio suma el corrimiento medido (-4, 0,1) a todas las casillas
        assert obtenido[0] + lab.corrimiento_mm[0] == pytest.approx(esperado[0], abs=1e-6)
        assert obtenido[1] + lab.corrimiento_mm[1] == pytest.approx(esperado[1], abs=1e-6)
    assert avisos == []


def test_con_tres_esquinas_alcanza_y_la_altura_sale_de_a1():
    superficie, _ = calibrar_superficie("t", {"a1": A1, "h1": H1, "a8": A8}, 8, 8)
    assert superficie.z_mm == pytest.approx(225.0079)


def test_falta_una_esquina():
    with pytest.raises(CeldaInvalida, match="a8"):
        calibrar_superficie("t", {"a1": A1, "h1": H1}, 8, 8)


def test_orientacion_distinta_se_rechaza():
    torcida = (*A8[:3], 150.0, 30.0, -80.0)
    with pytest.raises(CeldaInvalida, match="orientación"):
        calibrar_superficie("t", {"a1": A1, "h1": H1, "a8": torcida}, 8, 8)


def test_esquina_muy_por_encima_de_a1():
    alta = (A8[0], A8[1], A1[2] + 100, *A8[3:])
    with pytest.raises(CeldaInvalida, match="por encima de a1"):
        calibrar_superficie("t", {"a1": A1, "h1": H1, "a8": alta}, 8, 8)


def test_esquinas_colineales():
    with pytest.raises(CeldaInvalida, match="colineales"):
        calibrar_superficie("t", {"a1": (0, 0, 0), "h1": (100, 0, 0), "a8": (200, 0, 0)}, 8, 8)


def test_una_esquina_mal_centrada_avisa():
    mala = (H8[0] + 15, H8[1], *H8[2:])
    _, avisos = calibrar_superficie("t", {"a1": A1, "h1": H1, "a8": A8, "h8": mala}, 8, 8, z_mm=225.6)
    assert any("revisá si está bien centrada" in a for a in avisos)


def test_sin_altura_no_se_puede():
    with pytest.raises(CeldaInvalida, match="altura"):
        calibrar_superficie("t", {"a1": (0, 0), "h1": (100, 0), "a8": (0, 100)}, 4, 4)


# --- largo de la herramienta ----------------------------------------------------------------------------------------------------
def test_largo_por_apoyo():
    assert largo_por_apoyo(225.6, 8.6) == pytest.approx(217.0)
    with pytest.raises(CeldaInvalida, match="entre 0 y"):
        largo_por_apoyo(5, 20)


def test_pivote_recupera_el_vector_de_la_herramienta():
    azar = random.Random(11)
    t, c = np.array([2.0, -1.5, 217.0]), np.array([100.0, -500.0, 30.0])
    poses = []
    for _ in range(8):
        rx, ry, rz = azar.uniform(150, 210), azar.uniform(-35, 35), azar.uniform(-180, 180)
        R = rotacion_de_euler(rx, ry, rz)
        p = c - R @ t
        poses.append((*p, rx, ry, rz))
    r = calibrar_por_pivote(poses)
    assert r["vector_mm"] == pytest.approx(list(t), abs=1e-6) and r["largo_mm"] == pytest.approx(np.linalg.norm(t)) and r["residuo_mm"] < 1e-6
    assert r["punto_fijo_mm"] == pytest.approx(list(c), abs=1e-6)


def test_pivote_con_orientaciones_iguales_no_alcanza():
    poses = [(100 + i, -500, 250, 180, 0, 0) for i in range(4)]
    with pytest.raises(CeldaInvalida, match="demasiado parecidas"):
        calibrar_por_pivote(poses)


def test_pivote_con_pocas_poses():
    with pytest.raises(CeldaInvalida, match="al menos 3"):
        calibrar_por_pivote([(0, 0, 0, 180, 0, 0)] * 2)


# --- guardar un lugar llevando el brazo ---------------------------------------------------------------------------------------
def test_guardar_un_lugar_con_el_brazo(brazo: Brazo):
    brazo.mover_a(120, -480, 90)
    lugar = brazo.guardar_lugar("mi_lugar")
    assert (lugar["x"], lugar["y"], lugar["z"]) == pytest.approx((120, -480, 90), abs=0.1)
    assert brazo.celda.posicion_de("mi_lugar") == pytest.approx((120, -480, 90), abs=0.1)
    assert brazo.guardar_lugar("otro", z=12)["z"] == 12
    with pytest.raises(Exception, match="nombre del lugar"):
        brazo.guardar_lugar("con espacios!")
