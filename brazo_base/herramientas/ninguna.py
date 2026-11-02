"""Sin herramienta: el brazo solo se mueve. El TCP es la brida."""
from __future__ import annotations

from brazo_base.herramientas.base import Herramienta


class SinHerramienta(Herramienta):
    nombre = "ninguna"
    largo_mm = 0.0

    def conectar(self, cliente) -> None:
        pass

    def abrir(self) -> None:
        pass

    def cerrar(self) -> bool | None:
        return None

    def abrir_a(self, fraccion: float) -> None:
        pass

    def estado(self) -> dict:
        return {"herramienta": self.nombre}
