"""La cinemática del simulador (geometría del CAD oficial) y sus propiedades con la calibración real del ajedrez."""
import random
from pathlib import Path

import numpy as np
import pytest

from brazo_base.celda import cargar_celda
from brazo_base.seguridad.perfiles import Poses
from brazo_base.simulador import cinematica as c

DATOS = Path(__file__).parent / "datos"
DESCANSO = (298.4786, 35.3395, -150.676, 27.4337, 90.4496, -38.7623)


def test_el_descanso_real_deja_la_herramienta_apuntando_hacia_abajo():
    R, _ = c.fk(DESCANSO)
    assert R[:, 2] == pytest.approx((0, 0, -1), abs=0.05)  # J5 = 90°: la herramienta mira a la mesa


def test_en_pose_cero_el_brazo_esta_recto_y_la_brida_mira_de_lado():
    R, p = c.fk((0,) * 6)
    assert p[2] == pytest.approx(1047) and R[2, 2] == pytest.approx(0, abs=1e-9)


def test_ida_y_vuelta_de_pose_a_angulos():
    azar = random.Random(7)
    for _ in range(20):
        q = tuple(azar.uniform(-90, 90) for _ in range(6))
        pose = c.pose_para_angulos(q)
        resuelto = c.angulos_para_pose_completa(pose, q)
        assert resuelto is not None
        assert c.pose_para_angulos(resuelto)[:3] == pytest.approx(pose[:3], abs=0.1)


def test_euler_ida_y_vuelta():
    for rx, ry, rz in [(180, 0, 0), (177.8, -2.4, -82), (-90, 30, 45)]:
        assert c.euler_de_rotacion(c.rotacion_de_euler(rx, ry, rz)) == pytest.approx((rx, ry, rz), abs=1e-6) or c.rotacion_de_euler(*c.euler_de_rotacion(c.rotacion_de_euler(rx, ry, rz))) == pytest.approx(c.rotacion_de_euler(rx, ry, rz), abs=1e-9)


@pytest.mark.parametrize("casilla", ["a1", "e2", "h1", "a8", "h8", "e4"])
def test_las_casillas_del_tablero_real_se_alcanzan_con_la_muneca_a_90(casilla):
    poses = Poses(cargar_celda(DATOS / "celda_ajedrez" / "celda.json"))
    for sobre in (0, 90):
        q = c.angulos_para_pose_completa(poses.pose(f"tablero_ajedrez:{casilla}", sobre, "p"), DESCANSO)
        assert q is not None, f"{casilla} no se alcanza"
        assert q[4] == pytest.approx(90, abs=6)  # igual que el J5 = 90° del descanso real: la pinza mira a la mesa


def test_un_punto_imposible_da_none():
    assert c.angulos_para_pose(0, -2000, 300, 0) is None
