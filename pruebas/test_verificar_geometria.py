"""`herramientas/verificar_geometria.py` contra un controlador falso que calcula PositiveKin con el MISMO modelo (debe dar «coinciden») y con uno girado (debe decir cuánto)."""
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

import pytest

from brazo_base.simulador import cinematica
from brazo_base.simulador.protocolo import separar_comandos

RUTA = Path(__file__).parent.parent / "herramientas" / "verificar_geometria.py"


def cargar():
    especificacion = importlib.util.spec_from_file_location("verificar_geometria", RUTA)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def controlador(giro_base_grados=0.0):
    class Manejador(socketserver.BaseRequestHandler):
        def handle(self):
            import math
            while True:
                datos = self.request.recv(1024)
                if not datos:
                    return
                for comando in separar_comandos(datos.decode())[0]:
                    if comando.startswith("PositiveKin("):
                        q = [float(v) for v in comando[len("PositiveKin("):].split(",")[:6]]
                        x, y, z, rx, ry, rz = cinematica.pose_para_angulos(tuple(q))
                        a = math.radians(giro_base_grados)
                        x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
                        respuesta = f"0,{{{x:.6f},{y:.6f},{z:.6f},{rx:.6f},{ry:.6f},{rz:.6f}}},{comando};"
                    elif comando.startswith(("GetAngle", "GetPose")):
                        q = (10, 20, -30, 40, 50, 60)
                        valores = q if comando.startswith("GetAngle") else cinematica.pose_para_angulos(q)
                        respuesta = "0,{" + ",".join(f"{v:.6f}" for v in valores) + "}," + comando + ";"
                    else:
                        respuesta = f"-10000,{{}},{comando};"
                    self.request.sendall(respuesta.encode())

    servidor = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Manejador)
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def correr(servidor, capsys):
    modulo = cargar()
    argv = sys.argv
    sys.argv = ["verificar", "--host", "127.0.0.1", "--puerto", str(servidor.server_address[1])]
    try:
        codigo = modulo.main()
    finally:
        sys.argv = argv
        servidor.shutdown()
    return codigo, capsys.readouterr().out


def test_con_el_mismo_modelo_coinciden(capsys):
    codigo, salida = correr(controlador(), capsys)
    assert codigo == 0 and "El modelo es fiel" in salida and "8 de 8 coinciden" in salida


def test_si_la_base_esta_girada_lo_dice(capsys):
    codigo, salida = correr(controlador(giro_base_grados=90), capsys)
    assert codigo == 3 and "solo un giro de la base de 90.0°" in salida


def test_no_envia_nada_que_no_sea_una_consulta():
    modulo = cargar()
    with pytest.raises(ValueError, match="Solo se permiten consultas"):
        modulo.consultar(None, "MovJ(joint={0,0,0,0,0,0})")
