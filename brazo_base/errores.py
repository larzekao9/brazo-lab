"""Errores de la plataforma. Todos heredan de `ErrorBrazo` y su mensaje dice qué hacer."""
from __future__ import annotations


class ErrorBrazo(Exception):
    """Base de todos los errores de `brazo_base`."""


class SinConexion(ErrorBrazo):
    """Se pidió algo que necesita conexión y todavía no se llamó a `conectar()`."""


class NoHabilitado(ErrorBrazo):
    """El brazo está conectado pero no habilitado: llamá a `habilitar()` antes de mover."""


class RecorridoProhibido(ErrorBrazo):
    """El recorrido pasa por una zona prohibida, sale de la mesa o rompe un límite. No se movió nada."""

    def __init__(self, problemas: list[str]):
        self.problemas = problemas
        super().__init__("Recorrido prohibido, no se movió nada:\n  - " + "\n  - ".join(problemas))


class NoAgarro(ErrorBrazo):
    """La herramienta cerró y no sostiene nada: el objeto no estaba donde se esperaba o se cayó."""


class HerramientaNoResponde(ErrorBrazo):
    """La herramienta no contestó: revisá su alimentación y su cable, o inicializala."""


class ErrorDelControlador(ErrorBrazo):
    """El controlador rechazó un comando o el brazo salió del modo normal (alarma, colisión, pausa)."""


class CeldaInvalida(ErrorBrazo):
    """El archivo de la celda tiene un dato que no sirve."""
