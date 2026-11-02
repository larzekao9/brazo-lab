import pytest

from brazo_base import Brazo


@pytest.fixture
def brazo():
    """Brazo en el simulador, 25 veces más rápido que el tiempo real y con puerto elegido por el sistema (nunca uno fijo)."""
    with Brazo(velocidad_simulacion=25) as b:
        yield b
