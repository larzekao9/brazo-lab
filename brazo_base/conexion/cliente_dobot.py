"""Cliente TCP/IP del Dobot CR5AS (controlador V4): lo que se probó contra el brazo real, en una sola clase.

Sigue el manual "Dobot TCP/IP Remote Control Interface Guide V4.6.5": todos los comandos (control, ajustes y movimiento) van
como texto por el puerto 29999 y cada uno responde `ErrorID,{valores},Comando(...);`. Los de movimiento son comandos de COLA: el
controlador contesta apenas los recibe, no cuando terminan; para saber cuándo termina un movimiento se consulta `RobotMode()`
(7 y 8 = en movimiento, 5 = habilitado y libre). Este controlador no tiene `Sync`.

Seguridad: el cliente arranca siempre con la velocidad global baja (`velocidad_global`, 20 % por defecto), nunca manda
`PowerOn`/`EnableRobot` por su cuenta, corta con `Stop()` si algo falla a mitad de un movimiento y no deshabilita el brazo al
cerrar (un brazo deshabilitado frena sus articulaciones de golpe).
"""
from __future__ import annotations

import re
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass

MODO_LIBRE = 5
MODOS_EN_MOVIMIENTO = (7, 8)
COMANDOS_BLOQUEADOS_AL_CANCELAR = ("Mov", "RelMov", "SetHoldRegs")
MODOS_DE_FALLA = {9: "alarma activa", 10: "en pausa", 11: "colisión detectada"}
PATRON_VALORES = re.compile(r"\{(.*?)\}(?:,|$)")  # solo el primer par de llaves: el comando eco puede traer `pose={...}`


class ErrorDobot(RuntimeError):
    """El controlador devolvió un `ErrorID` distinto de 0, o el brazo salió del modo normal."""


@dataclass
class RespuestaDobot:
    """Respuesta ya separada: `error_id` (0 = aceptado), `valores` (lo que va entre llaves) y el comando eco."""

    error_id: int
    valores: str
    comando: str


def interpretar_respuesta(texto: str) -> RespuestaDobot:
    """Separa `ErrorID,{valores},Comando(...);`. Si no tiene ese formato (p. ej. `Control Mode Is Not Tcp`), da `ErrorDobot`."""
    limpio = texto.strip().rstrip(";").strip()
    primero, _, resto = limpio.partition(",")
    try:
        error_id = int(primero)
    except ValueError:
        raise ErrorDobot(f"Respuesta inesperada del controlador: {limpio!r}") from None
    coincidencia = PATRON_VALORES.match(resto)
    valores = coincidencia.group(1) if coincidencia else ""
    comando = resto[coincidencia.end():] if coincidencia else resto
    return RespuestaDobot(error_id, valores, comando)


def _lista(valores: str) -> tuple[float, ...]:
    return tuple(float(v) for v in valores.split(",") if v.strip())


RESPUESTA_SIN_MODO_TCP = b"Control Mode Is Not Tcp"
MENSAJE_SIN_MODO_TCP = (
    "El robot responde pero no está en modo de control TCP/IP: activalo en DobotStudio Pro (control remoto TCP/IP) y volvé a conectar"
)


class ClienteDobot:
    """Conexión por socket al dashboard del Dobot (puerto 29999) con los comandos que usa el proyecto."""

    def __init__(
        self,
        host: str,
        puerto: int = 29999,
        timeout_segundos: float = 5.0,
        velocidad_global: int = 20,
        aceleracion: int = 10,
        velocidad: int = 20,
    ):
        """
        Args:
            velocidad_global: `SpeedFactor` (1 a 100) que se fija al conectar. Empezar bajo (20).
            aceleracion, velocidad: porcentajes (1 a 100) que llevan por defecto los movimientos (`a=`, `v=`).
        """
        self.host, self.puerto, self.timeout_segundos = host, puerto, timeout_segundos
        self.velocidad_global, self.aceleracion, self.velocidad = velocidad_global, aceleracion, velocidad
        self._socket: socket.socket | None = None
        self._cerrojo = threading.RLock()
        self.historial: deque[dict] = deque(maxlen=80)
        """Los últimos comandos enviados (hora, hilo, comando y resultado): para ver en qué orden se cruzaron cuando algo falla (`GET /brazo/control/diagnostico`)."""
        """Un comando a la vez por el socket: el panel de control lee la telemetría mientras un hilo mueve el brazo."""
        self.cancelado = False

    def cancelar(self) -> None:
        """Parada del usuario: frena con `Stop()` y rechaza todo movimiento o comando de pinza posterior hasta `reanudar()`.

        Así una secuencia en curso (varios pasos en otro hilo) se corta de verdad: sin esto el siguiente paso volvería a mover el
        brazo, o abriría la pinza soltando la pieza en el aire.
        """
        self.cancelado = True
        self.detener()

    def reanudar(self) -> None:
        """Vuelve a aceptar movimientos (se llama al empezar una tarea nueva)."""
        self.cancelado = False

    # --- conexión ------------------------------------------------------------------------------------------------
    def conectar(self) -> None:
        """Abre el socket, comprueba que el brazo responde y fija la velocidad global. No lo enciende ni lo habilita."""
        self._socket = socket.create_connection((self.host, self.puerto), timeout=self.timeout_segundos)
        self._socket.settimeout(self.timeout_segundos)
        modo = self.modo()  # falla con ErrorDobot si no está en modo TCP
        self.enviar(f"SpeedFactor({self.velocidad_global})")
        if modo in MODOS_DE_FALLA:
            raise ErrorDobot(f"El brazo está en modo {modo} ({MODOS_DE_FALLA[modo]}): resolvelo antes de mover")

    def cerrar(self) -> None:
        """Cierra el socket. NO deshabilita el brazo."""
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def enviar(self, comando: str) -> RespuestaDobot:
        """Manda un comando, espera la respuesta completa (termina en `;`) y falla si el `ErrorID` no es 0."""
        try:
            respuesta = self._enviar(comando)
        except Exception as error:
            self._anotar(comando, f"ERROR {error}")
            raise
        self._anotar(comando, "ok")
        return respuesta

    def _anotar(self, comando: str, resultado: str) -> None:
        self.historial.append({"hora": time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}", "hilo": threading.current_thread().name, "comando": comando[:90], "resultado": resultado[:120]})

    def _enviar(self, comando: str) -> RespuestaDobot:
        if self.cancelado and comando.startswith(COMANDOS_BLOQUEADOS_AL_CANCELAR):
            raise ErrorDobot("Cancelado por el usuario")
        with self._cerrojo:
            if self._socket is None:
                raise RuntimeError("No hay conexión con el Dobot: llamá a conectar() primero")
            self._socket.sendall(comando.encode("ascii"))
            recibido = b""
            while not recibido.rstrip().endswith(b";"):
                trozo = self._socket.recv(1024)
                if not trozo:
                    raise ErrorDobot("El controlador cerró la conexión")
                recibido += trozo
                if RESPUESTA_SIN_MODO_TCP in recibido:  # esa respuesta no termina en `;`: sin esto se esperaría hasta el timeout
                    raise ErrorDobot(MENSAJE_SIN_MODO_TCP)
            respuesta = interpretar_respuesta(recibido.decode("ascii", errors="replace"))
            if respuesta.error_id != 0:
                raise ErrorDobot(f"{comando} -> ErrorID {respuesta.error_id}")
            return respuesta

    # --- lectura -------------------------------------------------------------------------------------------------
    def modo(self) -> int:
        """`RobotMode()`: 5 = habilitado y libre, 7/8 = moviéndose, 9 = alarma, 11 = colisión (ver el manual)."""
        return int(float(self.enviar("RobotMode()").valores))

    def pose(self) -> tuple[float, ...]:
        """`GetPose()`: `(x, y, z, rx, ry, rz)` en mm y grados."""
        return _lista(self.enviar("GetPose()").valores)

    def angulos(self) -> tuple[float, ...]:
        """`GetAngle()`: ángulos de las 6 articulaciones, en grados."""
        return _lista(self.enviar("GetAngle()").valores)

    def pose_con_herramienta(self, usuario: int = 0, herramienta: int = 0) -> tuple[float, ...]:
        """`GetPose(user=,tool=)`: la pose del sistema de usuario y la herramienta indicados (0 y 0 = la brida), sin cambiar los vigentes."""
        return _lista(self.enviar(f"GetPose(user={usuario},tool={herramienta})").valores)

    def cinematica_directa(self, angulos: list[float] | tuple[float, ...], usuario: int = 0, herramienta: int = 0) -> tuple[float, ...]:
        """`PositiveKin(j1..j6,user=,tool=)`: la pose `(x, y, z, rx, ry, rz)` que el controlador calcula para esos ángulos. No mueve el brazo."""
        cuerpo = ",".join(f"{a:g}" for a in angulos)
        return _lista(self.enviar(f"PositiveKin({cuerpo},user={usuario},tool={herramienta})").valores)

    # --- movimiento ----------------------------------------------------------------------------------------------
    def esperar_fin(self, limite_segundos: float = 30.0, intervalo: float = 0.1) -> None:
        """Bloquea hasta que el brazo vuelve a estar libre. Si pasa a alarma/pausa/colisión o se agota el tiempo, corta con `Stop()`."""
        inicio = time.monotonic()
        se_movio = False
        while time.monotonic() - inicio < limite_segundos:
            modo = self.modo()
            if modo in MODOS_DE_FALLA:
                self.detener()
                raise ErrorDobot(f"El brazo salió del modo normal: {MODOS_DE_FALLA[modo]} (modo {modo})")
            if modo in MODOS_EN_MOVIMIENTO:
                se_movio = True
            elif modo == MODO_LIBRE and (se_movio or time.monotonic() - inicio > 1.0):
                return
            time.sleep(intervalo)
        self.detener()
        raise TimeoutError("El movimiento no terminó a tiempo (se mandó Stop())")

    def detener(self) -> None:
        """`Stop()`: frena la cola de movimientos."""
        self.enviar("Stop()")

    def _opciones(self, aceleracion: int | None, velocidad: int | None) -> str:
        return f"a={aceleracion or self.aceleracion},v={velocidad or self.velocidad}"

    def mover_a_pose(
        self, pose: tuple[float, ...], lineal: bool = False, aceleracion: int | None = None, velocidad: int | None = None
    ) -> None:
        """Va a `(x, y, z, rx, ry, rz)` (en el usuario/herramienta 0) y espera a llegar. `lineal=True` usa `MovL`; si no, `MovJ`."""
        if len(pose) != 6:
            raise ValueError("La pose necesita 6 valores: x, y, z, rx, ry, rz")
        comando = "MovL" if lineal else "MovJ"
        cuerpo = ",".join(f"{valor:g}" for valor in pose)
        self.enviar(f"{comando}(pose={{{cuerpo}}},{self._opciones(aceleracion, velocidad)})")
        self.esperar_fin()

    def mover_a_angulos(
        self, angulos: tuple[float, ...], aceleracion: int | None = None, velocidad: int | None = None
    ) -> None:
        """Va a los 6 ángulos de articulación dados (`MovJ(joint=...)`) y espera a llegar. Sirve para la posición cero."""
        if len(angulos) != 6:
            raise ValueError("Se necesitan los 6 ángulos de las articulaciones")
        cuerpo = ",".join(f"{valor:g}" for valor in angulos)
        self.enviar(f"MovJ(joint={{{cuerpo}}},{self._opciones(aceleracion, velocidad)})")
        self.esperar_fin()

    def mover_relativo(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, velocidad_mm_s: int = 20) -> None:
        """Desplazamiento lineal relativo en el sistema de la base (`user=0`), a una velocidad absoluta baja en mm/s."""
        self.enviar(f"RelMovLUser({dx:g},{dy:g},{dz:g},0,0,0,user=0,a={self.aceleracion},speed={velocidad_mm_s})")
        self.esperar_fin()

    # --- enseñanza manual ----------------------------------------------------------------------------------------
    def activar_arrastre(self) -> None:
        """`StartDrag()`: deja las articulaciones sueltas para moverlas a mano. El brazo cede al peso: sostenelo."""
        self.enviar("StartDrag()")

    def desactivar_arrastre(self) -> None:
        """`StopDrag()`: vuelve al modo normal."""
        self.enviar("StopDrag()")
