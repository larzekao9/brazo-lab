from brazo_base import celda_demo


def test_ensayo_no_mueve_nada(brazo):
    antes = brazo.pose()
    r = brazo.ensayo("llevar", objeto="caja_roja", lugar="bandeja")
    assert r["ok"] and r["tramos"] and brazo.pose() == antes


def test_ensayo_dice_los_problemas(brazo):
    r = brazo.ensayo("mover", x=-450, y=-300, z=50)
    assert not r["ok"] and "tripode_camara" in r["problemas"][0]


def test_ensayo_de_articulaciones(brazo):
    assert not brazo.ensayo("articulaciones", angulos=[0, 0, 170, 0, 0, 0])["ok"]
