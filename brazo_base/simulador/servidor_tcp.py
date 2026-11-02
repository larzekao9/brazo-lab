"""Servidor TCP del dashboard: acepta conexiones y le pasa cada comando a `ProtocoloDobot`."""
from __future__ import annotations

import socketserver
import threading

from brazo_base.simulador.protocolo import ProtocoloDobot, SesionDashboard, separar_comandos


class _Manejador(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        protocolo: ProtocoloDobot = self.server.protocolo  # type: ignore[attr-defined]
        sesion, pendiente = SesionDashboard(), ""
        protocolo.simulador.registrar("sim", f"cliente conectado desde {self.client_address[0]}")
        try:
            while True:
                datos = self.request.recv(4096)
                if not datos:
                    break
                comandos, pendiente = separar_comandos(pendiente + datos.decode("ascii", errors="replace"))
                for comando in comandos:
                    self.request.sendall(protocolo.procesar(comando, sesion).encode("ascii", errors="replace"))
        except (ConnectionError, OSError):
            pass
        finally:
            protocolo.cerrar_sesion(sesion)
            protocolo.simulador.registrar("sim", "cliente desconectado")


class ServidorDashboard(socketserver.ThreadingTCPServer):
    """Escucha en `(host, puerto)`; con puerto 0 el sistema elige uno libre (`self.server_address[1]`)."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, protocolo: ProtocoloDobot, host: str = "127.0.0.1", puerto: int = 29999):
        self.protocolo = protocolo
        super().__init__((host, puerto), _Manejador)
        self._hilo: threading.Thread | None = None

    @property
    def puerto(self) -> int:
        return self.server_address[1]

    def iniciar(self) -> None:
        """Atiende conexiones en un hilo."""
        self._hilo = threading.Thread(target=self.serve_forever, name="dashboard-dobot", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self.shutdown()
        self.server_close()
