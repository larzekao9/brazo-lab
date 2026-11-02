"""El mundo del simulador en modo geométrico (sin física): objetos de la celda, los dedos de la pinza y lo que sostienen.

Es lo que `PinzaSimulada` necesita: `fijar_dedos`, `estado_dedos` y `fuerza_de_contacto_con_piezas_n`. Un objeto agarrable se sostiene cuando los
dedos, estando la punta dentro de su huella y a su altura, se cierran hasta su ancho de agarre; al abrirse se suelta y cae hasta lo que haya debajo
(la mesa u otro objeto). Un objeto mayor que la apertura de los dedos no se agarra. Limitación: no hay choques del resto del brazo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from brazo_base.celda.modelo import Celda, Objeto

TOLERANCIA_HORIZONTAL_MM = 8.0
TOLERANCIA_ALTURA_MM = 2.0
MARGEN_SOLTAR_MM = 0.5


@dataclass
class ObjetoSim:
    objeto: Objeto
    x: float
    y: float
    z: float  # base
    sostenido: bool = False

    @property
    def tope(self) -> float:
        return self.z + self.objeto.alto


@dataclass
class MundoGeometrico:
    celda: Celda
    carrera_mm: float = 26.0
    objetos: dict[str, ObjetoSim] = field(init=False)
    ancho_mm: float = field(init=False)
    objetivo_mm: float = field(init=False)
    fuerza_n: float = 0.0
    velocidad_mm_s: float = 40.0
    velocidad_actual: float = 0.0
    sostiene: ObjetoSim | None = None
    _desfase_z: float = 0.0
    tcp: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        self.ancho_mm = self.objetivo_mm = self.carrera_mm
        self.objetos = {n: ObjetoSim(o, *o.posicion) for n, o in self.celda.objetos.items()}

    # --- lo que usa la pinza simulada --------------------------------------------------------------------------------------
    def fijar_dedos(self, ancho_mm: float, fuerza_n: float, velocidad_mm_s: float) -> None:
        self.objetivo_mm, self.fuerza_n, self.velocidad_mm_s = max(0.0, min(self.carrera_mm, ancho_mm)), fuerza_n, velocidad_mm_s

    def estado_dedos(self) -> tuple[float, float]:
        return self.ancho_mm, self.velocidad_actual

    def fuerza_de_contacto_con_piezas_n(self) -> float:
        return self.fuerza_n if self.sostiene is not None else 0.0

    # --- avance --------------------------------------------------------------------------------------------------------------
    def paso(self, dt: float, tcp: tuple[float, float, float]) -> None:
        """Avanza `dt` segundos de simulación: mueve los dedos, agarra, lleva y suelta."""
        self.tcp = tcp
        anterior = self.ancho_mm
        if self.sostiene is not None:
            self._mover_sostenido(tcp)
            if self.objetivo_mm > self.sostiene.objeto.ancho_agarre_mm + MARGEN_SOLTAR_MM:
                self._soltar()
        meta = self.objetivo_mm
        if self.sostiene is not None:
            meta = max(meta, self.sostiene.objeto.ancho_agarre_mm)
        else:
            candidato = self._candidato_a_agarrar()
            if candidato is not None and meta < self.ancho_mm:
                meta = max(meta, candidato.objeto.ancho_agarre_mm)
        paso_max = self.velocidad_mm_s * dt
        self.ancho_mm += max(-paso_max, min(paso_max, meta - self.ancho_mm))
        self.velocidad_actual = (self.ancho_mm - anterior) / dt if dt > 0 else 0.0
        if self.sostiene is None and self.objetivo_mm < self.ancho_mm + 1e-6:
            candidato = self._candidato_a_agarrar()
            if candidato is not None and abs(self.ancho_mm - candidato.objeto.ancho_agarre_mm) < 1e-6 and self.objetivo_mm < candidato.objeto.ancho_agarre_mm:
                self._agarrar(candidato)

    def _candidato_a_agarrar(self) -> ObjetoSim | None:
        x, y, z = self.tcp
        mejor, mejor_d = None, None
        for o in self.objetos.values():
            if not o.objeto.agarrable or o.sostenido:
                continue
            d = ((o.x - x) ** 2 + (o.y - y) ** 2) ** 0.5
            if d <= o.objeto.radio_horizontal_mm * 0.5 + TOLERANCIA_HORIZONTAL_MM and o.z - TOLERANCIA_ALTURA_MM <= z <= o.tope + TOLERANCIA_ALTURA_MM:
                if self.ancho_mm >= o.objeto.ancho_agarre_mm - 1e-6 and (mejor_d is None or d < mejor_d):
                    mejor, mejor_d = o, d
        return mejor

    def _agarrar(self, o: ObjetoSim) -> None:
        self.sostiene, o.sostenido = o, True
        self._desfase_z = self.tcp[2] - o.z

    def _mover_sostenido(self, tcp: tuple[float, float, float]) -> None:
        o = self.sostiene
        o.x, o.y, o.z = tcp[0], tcp[1], tcp[2] - self._desfase_z

    def _soltar(self) -> None:
        o, self.sostiene = self.sostiene, None
        o.sostenido = False
        o.z = self._soporte_bajo(o)

    def perder_objeto(self) -> bool:
        """Fallo provocado: el objeto se cae de los dedos."""
        if self.sostiene is None:
            return False
        self._soltar()
        return True

    def _soporte_bajo(self, o: ObjetoSim) -> float:
        """Altura donde queda apoyado `o`: la mesa, una superficie de la celda o el tope de otro objeto debajo."""
        suelo = self.celda.mesa_z_mm
        for sup in self.celda.superficies.values():
            if sup.z_mm <= o.z + TOLERANCIA_ALTURA_MM + 1.0:
                suelo = max(suelo, sup.z_mm)
        for otro in self.objetos.values():
            if otro is o or otro.sostenido:
                continue
            if ((otro.x - o.x) ** 2 + (otro.y - o.y) ** 2) ** 0.5 < (otro.objeto.radio_horizontal_mm + o.objeto.radio_horizontal_mm) * 0.5 and otro.tope <= o.z + TOLERANCIA_ALTURA_MM + 1.0:
                suelo = max(suelo, otro.tope)
        return suelo

    def posiciones(self) -> dict[str, tuple[float, float, float]]:
        return {n: (o.x, o.y, o.z) for n, o in self.objetos.items()}
