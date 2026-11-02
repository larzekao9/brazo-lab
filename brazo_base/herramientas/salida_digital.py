"""Ventosa o pinza neumática accionada por una salida digital del controlador (`DO(pin, valor)`)."""
from __future__ import annotations

from brazo_base.herramientas.base import Herramienta


class SalidaDigital(Herramienta):
    """`cerrar` pone la salida en 1 y `abrir` en 0. No sabe si sostiene algo (devuelve `None`)."""

    def __init__(self, pin: int, largo_mm: float = 0.0, nombre: str = "salida_digital", modelo_3d: str | None = None):
        self.pin, self.largo_mm, self.nombre, self.modelo_3d = pin, largo_mm, nombre, modelo_3d
        self._cliente = None
        self._cerrada = False

    def conectar(self, cliente) -> None:
        self._cliente = cliente

    def _poner(self, valor: int) -> None:
        if self._cliente is None:
            raise RuntimeError("La herramienta no está conectada: llamá a brazo.conectar() primero")
        self._cliente.enviar(f"DO({self.pin},{valor})")
        self._cerrada = bool(valor)

    def abrir(self) -> None:
        self._poner(0)

    def cerrar(self) -> bool | None:
        self._poner(1)
        return None

    def abrir_a(self, fraccion: float) -> None:
        self._poner(0 if fraccion >= 0.5 else 1)

    def estado(self) -> dict:
        return {"herramienta": self.nombre, "cerrada": self._cerrada}
