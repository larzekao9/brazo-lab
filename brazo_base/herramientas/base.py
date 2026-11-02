"""Interfaz que cumple cualquier herramienta (pinza, ventosa, nada) del brazo."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Herramienta(ABC):
    """Una herramienta montada en la brida del brazo.

    `largo_mm` es la distancia de la brida a la punta: define el TCP (punto central de la herramienta). Las poses que ve el estudiante
    están siempre en el TCP; la plataforma suma `largo_mm` para hablarle al controlador, que trabaja con la brida.
    """

    nombre: str = "herramienta"
    largo_mm: float = 0.0
    modelo_3d: str | None = None

    @abstractmethod
    def conectar(self, cliente) -> None:
        """Prepara la herramienta con el `ClienteDobot` ya conectado."""

    def inicializar(self) -> None:
        """Deja la herramienta lista para usarse (algunas no necesitan nada)."""

    def desconectar(self) -> None:
        """Libera lo que `conectar` abrió."""

    @abstractmethod
    def abrir(self) -> None: ...

    @abstractmethod
    def cerrar(self) -> bool | None:
        """Cierra. `True` si sostiene algo, `False` si no, `None` si la herramienta no lo sabe."""

    @abstractmethod
    def abrir_a(self, fraccion: float) -> None:
        """`0` cerrada, `1` abierta del todo."""

    @abstractmethod
    def estado(self) -> dict: ...
