"""El simulador del controlador: pose del brazo que se mueve en el tiempo, cola de movimientos, pinza, mundo, fallos y registro de comandos.

Un hilo avanza la simulación a `escala_tiempo` veces el tiempo real (o se la avanza a mano con `avanzar`, en los tests). El estado se protege con
`cerrojo`. La cinemática es ESQUEMÁTICA (ver `cinematica.py`): herramienta siempre vertical y sin límites reales de articulación.
Las poses que maneja el simulador son las de la BRIDA, igual que el controlador real; el TCP es la brida menos el largo de la herramienta.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from brazo_base.celda.modelo import Celda
from brazo_base.simulador import cinematica
from brazo_base.simulador.mundo import MundoGeometrico
from brazo_base.simulador.parametros import ParametrosSimulador
from brazo_base.simulador.pinza_simulada import PinzaSimulada

MODO_APAGADO, MODO_DESHABILITADO, MODO_LIBRE, MODO_ARRASTRE, MODO_EJECUTANDO = 3, 4, 5, 6, 7
MODO_ALARMA, MODO_PAUSA, MODO_COLISION = 9, 10, 11
PASO_S = 1.0 / 60.0
MAXIMO_PASOS_POR_CICLO = 600
Pose = tuple[float, float, float, float, float, float]
POSE_DESCANSO_ANGULOS = (298.4786, 35.3395, -150.676, 27.4337, 90.4496, -38.7623)
"""Postura inicial si la celda no tiene un punto `descanso` con ángulos: la posición cero que se enseñó en el laboratorio."""
PASO_RUTA_MM = 10.0
"""Cada cuántos mm se resuelve la cinemática inversa a lo largo de un `MovL` (se hace al encolar, no en cada paso de tiempo)."""


class ErrorDeComando(Exception):
    """Un comando que el controlador rechazaría; `codigo` es el `ErrorID` que se devuelve."""

    def __init__(self, codigo: int, motivo: str = ""):
        super().__init__(motivo)
        self.codigo, self.motivo = codigo, motivo


@dataclass
class Fallos:
    """Fallos que se pueden provocar a mano para practicar."""

    no_tcp: bool = False
    alarma: bool = False
    colision: bool = False
    pinza_no_responde: bool = False


@dataclass
class Movimiento:
    identificador: int
    inicio_pose: Pose
    inicio_angulos: tuple[float, ...]
    fin_pose: Pose
    fin_angulos: tuple[float, ...]
    articular: bool
    duracion: float
    transcurrido: float = 0.0
    ruta: list[tuple[float, ...]] | None = None
    """Ángulos de cada punto de la recta de un `MovL` (resueltos al encolar): la brida sigue la recta y no una curva."""


def _mezclar_orientacion(inicio: Pose, fin: Pose, f: float) -> tuple[float, float, float]:
    """Orientación intermedia (rx, ry, rz) entre dos poses, por el camino angular corto."""
    return tuple(a + (((b - a + 180.0) % 360.0) - 180.0) * f for a, b in zip(inicio[3:], fin[3:]))


def _suave(s: float) -> float:
    return s * s * (3 - 2 * s)


class Simulador:
    def __init__(self, celda: Celda, escala_tiempo: float = 1.0, parametros: ParametrosSimulador | None = None, automatico: bool = True):
        self.celda = celda
        self.parametros = parametros or ParametrosSimulador()
        self.escala_tiempo = escala_tiempo
        self.cerrojo = threading.RLock()
        self.fallos = Fallos()
        self.control_tcp = True
        self.encendido = False
        self.habilitado = False
        self.arrastrando = False
        self.pausa_robot = False
        self.velocidad_global = 100
        self.largo_herramienta_mm = celda.largo_herramienta_mm
        self.historial: deque[dict] = deque(maxlen=300)
        self.mundo = MundoGeometrico(celda, carrera_mm=self.parametros.fisicos.carrera_mm)
        self.pinza = PinzaSimulada(self.mundo, self.parametros.fisicos, self.registrar)
        inicial = celda.puntos.get("descanso", {}).get("angulos")
        self.angulos: tuple[float, ...] = tuple(float(a) for a in inicial) if inicial and len(inicial) == 6 else POSE_DESCANSO_ANGULOS
        self.pose: Pose = cinematica.pose_para_angulos(self.angulos)
        self._rotacion = cinematica.fk(self.angulos)[0]
        self.cola: deque[Movimiento] = deque()
        self.actual: Movimiento | None = None
        self.siguiente_id = 1
        self.tiempo = 0.0
        self._hilo: threading.Thread | None = None
        self._detener_hilo = threading.Event()
        if automatico:
            self.iniciar()

    # --- vida del hilo -------------------------------------------------------------------------------------------------------
    def iniciar(self) -> None:
        if self._hilo is not None:
            return
        self._detener_hilo.clear()
        self._hilo = threading.Thread(target=self._bucle, name="simulador-dobot", daemon=True)
        self._hilo.start()

    def apagar(self) -> None:
        self._detener_hilo.set()
        if self._hilo is not None:
            self._hilo.join(timeout=2)
            self._hilo = None

    def _bucle(self) -> None:
        anterior = time.monotonic()
        while not self._detener_hilo.is_set():
            time.sleep(0.005)
            ahora = time.monotonic()
            simulado = (ahora - anterior) * self.escala_tiempo
            anterior = ahora
            self.avanzar(simulado)

    def registrar(self, origen: str, texto: str) -> None:
        self.historial.append({"t": round(self.tiempo, 3), "origen": origen, "texto": texto[:200]})

    # --- estado ----------------------------------------------------------------------------------------------------------------
    def modo(self) -> int:
        if self.fallos.alarma:
            return MODO_ALARMA
        if self.fallos.colision:
            return MODO_COLISION
        if not self.encendido:
            return MODO_APAGADO
        if not self.habilitado:
            return MODO_DESHABILITADO
        if self.pausa_robot:
            return MODO_PAUSA
        if self.arrastrando:
            return MODO_ARRASTRE
        if self.actual is not None or self.cola:
            return MODO_EJECUTANDO
        return MODO_LIBRE

    def tcp(self) -> tuple[float, float, float]:
        """Posición de la punta de la herramienta: la brida más el largo a lo largo del eje de la herramienta (con la orientación real del brazo)."""
        punta = self.pose[:3] + self._rotacion[:, 2] * self.largo_herramienta_mm
        return float(punta[0]), float(punta[1]), float(punta[2])

    def telemetria(self) -> dict:
        with self.cerrojo:
            x, y, z = self.tcp()
            return {"modo": self.modo(), "pose_brida": list(self.pose), "tcp": [x, y, z], "angulos": list(self.angulos), "tiempo": self.tiempo,
                    "pinza": {"ancho_mm": self.pinza.ancho_mm, "agarre": self.pinza.agarre},
                    "objetos": {n: list(p) for n, p in self.mundo.posiciones().items()},
                    "sostiene": self.mundo.sostiene.objeto.nombre if self.mundo.sostiene else None}

    # --- fallos ----------------------------------------------------------------------------------------------------------------
    def provocar(self, fallo: str, activo: bool = True) -> None:
        """`alarma`, `colision`, `no_tcp`, `pinza_no_responde` o `pieza_cae` (suelta lo que sostiene)."""
        with self.cerrojo:
            if fallo == "pieza_cae":
                if self.mundo.perder_objeto():
                    self.registrar("sim", "fallo provocado: se cayó lo que sostenía la pinza")
                return
            if not hasattr(self.fallos, fallo):
                raise ValueError(f"Fallo desconocido «{fallo}»")
            setattr(self.fallos, fallo, activo)
            if fallo in ("alarma", "colision") and activo:
                self.detener()
            self.registrar("sim", f"fallo {fallo} {'activado' if activo else 'desactivado'}")

    def limpiar_errores(self) -> None:
        self.fallos.alarma = self.fallos.colision = False

    # --- órdenes ---------------------------------------------------------------------------------------------------------------
    def _exigir_listo(self) -> None:
        if self.fallos.alarma or self.fallos.colision:
            raise ErrorDeComando(-2, "hay una alarma o colisión activa: limpiala con ClearError()")
        if not self.habilitado:
            raise ErrorDeComando(-1, "el brazo no está habilitado")

    def _punta_de(self, angulos: tuple[float, ...]) -> tuple[float, float, float]:
        """Punta de la herramienta para unos ángulos (con la orientación que da la cinemática)."""
        R, p = cinematica.fk(angulos)
        punta = p + R[:, 2] * self.largo_herramienta_mm
        return float(punta[0]), float(punta[1]), float(punta[2])

    def _encolar(self, m: Movimiento) -> int:
        self.cola.append(m)
        self.registrar("sim", f"movimiento {m.identificador} en cola ({m.duracion:.2f} s)")
        return m.identificador

    def _ultimo_estado(self) -> tuple[Pose, tuple[float, ...]]:
        if self.cola:
            return self.cola[-1].fin_pose, self.cola[-1].fin_angulos
        if self.actual:
            return self.actual.fin_pose, self.actual.fin_angulos
        return self.pose, self.angulos

    def _fijo(self, v: float) -> float:
        return max(1.0, v) / 100.0 * self.velocidad_global / 100.0

    def encolar_pose(self, pose, articular: bool, velocidad: float, aceleracion: float, velocidad_abs: float | None = None) -> int:
        """`MovJ/MovL(pose=...)`: la pose es la de la brida. Falla si está fuera de alcance o la punta entraría en la mesa.

        `MovL` resuelve la cinemática inversa cada `PASO_RUTA_MM` a lo largo de la recta, siguiendo la misma solución del brazo, para que la brida vaya
        derecho (es lo que validan las zonas) en vez de por una curva en el espacio de articulaciones.
        """
        with self.cerrojo:
            self._exigir_listo()
            pose = tuple(float(v) for v in pose)
            inicio_pose, inicio_ang = self._ultimo_estado()
            distancia = math.dist(inicio_pose[:3], pose[:3])
            if articular:
                angulos = cinematica.angulos_para_pose_completa(pose, inicio_ang)
                ruta = None
            else:
                puntos = max(1, math.ceil(distancia / PASO_RUTA_MM))
                ruta, previo = [], inicio_ang
                angulos = None
                for k in range(1, puntos + 1):
                    f = k / puntos
                    intermedia = tuple(a + (b - a) * f for a, b in zip(inicio_pose[:3], pose[:3])) + (pose[3:] if k == puntos else _mezclar_orientacion(inicio_pose, pose, f))
                    angulos = cinematica.angulos_para_pose_completa(intermedia, previo, alternativas=(k == 1))
                    if angulos is None:
                        break
                    ruta.append(angulos)
                    previo = angulos
            if angulos is None:
                raise ErrorDeComando(-1, f"la pose ({pose[0]:.0f}, {pose[1]:.0f}, {pose[2]:.0f}) está fuera del alcance del brazo (o el camino recto no es posible)")
            if self._punta_de(angulos)[2] < self.celda.mesa_z_mm - 1.0:
                raise ErrorDeComando(-1, "la punta de la herramienta quedaría dentro de la mesa")
            fin = cinematica.pose_para_angulos(angulos)
            if articular:
                dur = self._duracion_articular(inicio_ang, angulos, velocidad)
            else:
                v_mm_s = velocidad_abs if velocidad_abs else self.parametros.robot.velocidad_lineal_max_mm_s * self._fijo(velocidad)
                dur = max(distancia / max(v_mm_s, 1.0), self._duracion_articular(inicio_ang, angulos, 100) * 0.5)
            identificador = self.siguiente_id
            self.siguiente_id += 1
            return self._encolar(Movimiento(identificador, inicio_pose, inicio_ang, fin, angulos, articular, max(dur, self.parametros.robot.duracion_minima_s), ruta=ruta))

    def encolar_angulos(self, angulos, velocidad: float, aceleracion: float) -> int:
        with self.cerrojo:
            self._exigir_listo()
            angulos = tuple(float(v) for v in angulos)
            fin_pose = cinematica.pose_para_angulos(angulos)
            if self._punta_de(angulos)[2] < self.celda.mesa_z_mm - 1.0:
                raise ErrorDeComando(-1, "la punta de la herramienta quedaría dentro de la mesa")
            inicio_pose, inicio_ang = self._ultimo_estado()
            dur = self._duracion_articular(inicio_ang, angulos, velocidad)
            identificador = self.siguiente_id
            self.siguiente_id += 1
            return self._encolar(Movimiento(identificador, inicio_pose, inicio_ang, fin_pose, angulos, True, max(dur, self.parametros.robot.duracion_minima_s)))

    def _duracion_articular(self, desde, hasta, velocidad: float) -> float:
        mayor = max(abs(b - a) for a, b in zip(desde, hasta))
        return mayor / (self.parametros.robot.velocidad_articular_max_grados_s * self._fijo(velocidad))

    def pose_para_relativo(self, dx: float, dy: float, dz: float) -> Pose:
        pose, _ = self._ultimo_estado()
        return (pose[0] + dx, pose[1] + dy, pose[2] + dz, pose[3], pose[4], pose[5])

    def detener(self) -> None:
        """`Stop()`: descarta la cola y deja el brazo donde está."""
        self.cola.clear()
        self.actual = None

    # --- avance del tiempo -----------------------------------------------------------------------------------------------------
    def avanzar(self, segundos: float) -> None:
        """Avanza la simulación (en segundos simulados) en pasos fijos."""
        with self.cerrojo:
            pasos = min(MAXIMO_PASOS_POR_CICLO, max(0, int(round(segundos / PASO_S)))) if segundos >= PASO_S * 0.5 else 0
            restante = segundos - pasos * PASO_S
            for _ in range(pasos):
                self._paso(PASO_S)
            if restante > 1e-9 and pasos == 0:
                self._paso(restante)

    def _actualizar_pose(self) -> None:
        self._rotacion = cinematica.fk(self.angulos)[0]
        self.pose = cinematica.pose_para_angulos(self.angulos)

    def _paso(self, dt: float) -> None:
        self.tiempo += dt
        if self.habilitado and not self.pausa_robot and not self.arrastrando and not (self.fallos.alarma or self.fallos.colision):
            if self.actual is None and self.cola:
                self.actual = self.cola.popleft()
            m = self.actual
            if m is not None:
                m.transcurrido += dt
                s = _suave(min(1.0, m.transcurrido / m.duracion))
                if m.ruta:
                    posicion = s * len(m.ruta)
                    k = min(int(posicion), len(m.ruta) - 1)
                    desde = m.ruta[k - 1] if k > 0 else m.inicio_angulos
                    f = min(1.0, posicion - k)
                    self.angulos = tuple(a + (b - a) * f for a, b in zip(desde, m.ruta[k]))
                else:
                    self.angulos = tuple(a + (b - a) * s for a, b in zip(m.inicio_angulos, m.fin_angulos))
                self._actualizar_pose()
                if m.transcurrido >= m.duracion:
                    self.angulos = m.fin_angulos
                    self._actualizar_pose()
                    self.actual = None
        self.mundo.paso(dt, self.tcp())
        self.pinza.actualizar(self.tiempo)
