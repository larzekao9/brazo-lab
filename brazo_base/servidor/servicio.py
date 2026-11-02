"""El estado del servidor: un solo `Brazo` (la plataforma es la única dueña del brazo), la tarea en curso y la telemetría."""
from __future__ import annotations

import threading
import time

from brazo_base import Brazo, Celda, ErrorBrazo
from brazo_base.celda.archivos import celda_a_dict
from brazo_base.seguridad import geometria


class Conflicto(ErrorBrazo):
    """Pedido en un estado incorrecto (ya hay una tarea en curso, no hay conexión…)."""


class ServicioBrazo:
    def __init__(self) -> None:
        self.brazo: Brazo | None = None
        self.tarea: dict = {"id": 0, "nombre": None, "estado": "libre", "error": None, "resultado": None}
        self._cerrojo = threading.RLock()
        self._hilo: threading.Thread | None = None

    # --- conexión ---------------------------------------------------------------------------------------------------------
    def conectar(self, destino: str = "simulador", celda: str | None = None, velocidad: int | None = None, velocidad_simulacion: float = 1.0) -> None:
        with self._cerrojo:
            if self.brazo is not None:
                raise Conflicto("Ya hay una conexión: desconectá primero")
            brazo = Brazo(destino=destino, celda=celda, velocidad=velocidad, velocidad_simulacion=velocidad_simulacion)
            brazo.conectar()
            self.brazo = brazo

    def desconectar(self) -> None:
        with self._cerrojo:
            if self.brazo is None:
                return
            self.brazo.parar()
            hilo = self._hilo
        if hilo is not None:
            hilo.join(timeout=5)
        with self._cerrojo:
            self.brazo.desconectar()
            self.brazo = None
            self.tarea = {**self.tarea, "estado": "libre"}

    def exigir_brazo(self) -> Brazo:
        if self.brazo is None:
            raise Conflicto("No hay conexión: llamá a POST /conectar primero")
        return self.brazo

    # --- tareas -----------------------------------------------------------------------------------------------------------
    def lanzar(self, nombre: str, accion) -> dict:
        """Corre `accion(brazo)` en un hilo y devuelve la tarea (202). Solo una a la vez; `parar` siempre funciona."""
        with self._cerrojo:
            brazo = self.exigir_brazo()
            if self.tarea["estado"] == "en_curso":
                raise Conflicto(f"Ya hay una tarea en curso («{self.tarea['nombre']}»): esperá a que termine o llamá a POST /parar")
            self.tarea = {"id": self.tarea["id"] + 1, "nombre": nombre, "estado": "en_curso", "error": None, "resultado": None}
            numero = self.tarea["id"]

            def correr() -> None:
                try:
                    resultado = accion(brazo)
                    final = {"estado": "terminada", "resultado": resultado}
                except ErrorBrazo as error:
                    final = {"estado": "error", "error": str(error)}
                except Exception as error:  # una tarea nunca tumba el servidor
                    final = {"estado": "error", "error": f"{type(error).__name__}: {error}"}
                with self._cerrojo:
                    if self.tarea["id"] == numero:
                        if self.tarea.get("cancelada"):
                            final = {"estado": "cancelada", "error": None}
                        self.tarea = {**self.tarea, **final}

            self._hilo = threading.Thread(target=correr, name=f"tarea-{numero}", daemon=True)
            self._hilo.start()
            return dict(self.tarea)

    def parar(self) -> None:
        with self._cerrojo:
            brazo = self.exigir_brazo()
            if self.tarea["estado"] == "en_curso":
                self.tarea = {**self.tarea, "cancelada": True}
        brazo.parar()

    # --- lectura ----------------------------------------------------------------------------------------------------------
    def _dibujo_del_brazo(self, brazo: Brazo, angulos) -> list[list[float]]:
        """Puntos (mm) para dibujar el brazo: base, hombro, codo, muñecas, brida y punta, con la geometría del URDF (la misma en simulador y real)."""
        largo = brazo.largo_mm
        p = geometria.puntos_del_brazo(angulos, largo / 1000 if largo else geometria.LARGO_PINZA_DEFECTO)
        return [list(a * 1000) for a in p["articulaciones"]] + [list(p["punta"] * 1000)]

    def estado(self) -> dict:
        with self._cerrojo:
            tarea = {k: v for k, v in self.tarea.items() if k != "cancelada"}
            brazo = self.brazo
        if brazo is None:
            return {"conectado": False, "tarea": tarea}
        base: dict = {"conectado": True, "tarea": tarea}
        try:
            estado = brazo.estado()
            base.update(estado)
            base["brazo_puntos"] = self._dibujo_del_brazo(brazo, estado["angulos"])
            base["objetos"] = {n: list(p) for n, p in brazo.posiciones_objetos().items()}
        except ErrorBrazo as error:
            base["error_lectura"] = str(error)
        except OSError as error:
            base["error_lectura"] = f"Se perdió la conexión: {error}"
        base["hora"] = time.time()
        return base

    def celda(self) -> dict:
        brazo = self.exigir_brazo()
        return {**celda_a_dict(brazo.celda), "avisos": brazo.celda.avisos, "herramienta_config": brazo.celda.herramienta_config}


servicio = ServicioBrazo()
