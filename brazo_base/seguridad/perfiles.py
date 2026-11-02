"""Poses del pick and place por perfiles de agarre: de un lugar de la celda a la pose de la brida que se le manda al controlador.

Son las mismas cuentas de `EjecutorReal._pose` del ajedrez (probadas con el brazo real), sin nada de ajedrez: un «tipo de pieza» pasa a ser un
perfil (`celda.perfiles`) y el tablero, una superficie (`celda.superficies`). Todo en el sistema de la brida con la orientación enseñada.
"""
from __future__ import annotations

from brazo_base.celda.modelo import Celda
from brazo_base.errores import CeldaInvalida

MARGEN_AGARRE_DEFECTO_MM = 3.0
AIRE_SOBRE_EL_BORDE_MM = 2.0
"""Cuánto más arriba que el marco del tablero quedan los dedos en las casillas del borde."""


class Poses:
    def __init__(self, celda: Celda):
        if celda.orientacion is None:
            raise CeldaInvalida("Falta la orientacion [rx, ry, rz] de la herramienta en la celda: tomala de GetPose() con la pinza apuntando a la mesa")
        self.celda, self.agarre = celda, celda.agarre

    # --- perfiles ---------------------------------------------------------------------------------------------------------
    def perfil(self, nombre: str) -> dict:
        if nombre in self.celda.perfiles:
            return self.celda.perfiles[nombre]
        if "defecto" in self.celda.perfiles:
            return self.celda.perfiles["defecto"]
        raise CeldaInvalida(f"No hay un perfil de agarre «{nombre}» en la celda (ni «defecto»). Perfiles: {', '.join(self.celda.perfiles) or 'ninguno'}")

    def margen(self, perfil: str) -> float:
        """Cuánto sobre la superficie quedan los dedos al agarrar (mm)."""
        return float(self.perfil(perfil).get("margen_mm", self.agarre.get("margen_agarre_mm", MARGEN_AGARRE_DEFECTO_MM)))

    def apertura(self, perfil: str) -> float:
        """Apertura de la pinza al bajar (0 a 1). Falta = error: bajar con una apertura chica puede romper la pieza."""
        p = self.perfil(perfil)
        if "apertura" not in p:
            raise CeldaInvalida(f"Falta la apertura de la pinza en el perfil «{perfil}»: medí el ancho máximo del objeto y agregala")
        return float(p["apertura"])

    def giro(self, perfil: str) -> float:
        return float(self.perfil(perfil).get("giro_grados", self.agarre.get("giro_grados", 0.0)))

    def apertura_al_soltar(self, perfil: str) -> float:
        """Se abre más que al agarrar para dejar los dedos lejos del objeto (tope 1)."""
        return min(1.0, self.apertura(perfil) + float(self.agarre.get("apertura_extra_soltar", 0.25)))

    # --- lugares ----------------------------------------------------------------------------------------------------------
    def _lugar(self, lugar: str) -> tuple[float, float, float, bool, float]:
        """`(x, y, z_superficie, es_borde, desnivel_mm)`."""
        if ":" in lugar:
            nombre, casilla = lugar.split(":", 1)
            if nombre in self.celda.superficies:
                s = self.celda.superficies[nombre]
                x, y, z = s.lugar(casilla)
                return x, y, z, bool(s.borde_mm) and s.es_borde(casilla), 0.0
        if lugar in self.celda.lugares:
            d = self.celda.lugares[lugar]
            if "x" not in d:
                raise CeldaInvalida(f"El lugar «{lugar}» no tiene posición propia (x, y)")
            z = d.get("z", self.agarre.get("z_referencia_mm"))
            if z is None:
                raise CeldaInvalida(f"Falta la altura de «{lugar}»: ponele «z» al lugar o «z_referencia_mm» en agarre (la altura de la superficie)")
            return float(d["x"]), float(d["y"]), float(z), False, float(d.get("desnivel_mm", 0.0))
        conocidos = sorted({*self.celda.lugares, *self.celda.superficies})
        raise CeldaInvalida(f"No conozco el lugar «{lugar}». Lugares y superficies: {', '.join(conocidos) or 'ninguno'}")

    def borde_mm_de(self, lugar: str) -> float:
        nombre = lugar.split(":", 1)[0]
        return self.celda.superficies[nombre].borde_mm if nombre in self.celda.superficies else 0.0

    # --- poses ------------------------------------------------------------------------------------------------------------
    def pose(self, lugar: str, sobre_mm: float = 0.0, perfil: str = "defecto") -> tuple[float, float, float, float, float, float]:
        """Pose de la brida sobre `lugar`: altura de agarre del perfil más `sobre_mm`, con el giro del perfil."""
        x, y, z_sup, es_borde, _ = self._lugar(lugar)
        rx, ry, rz = self.celda.orientacion
        z = z_sup + self.margen(perfil) + sobre_mm
        if es_borde:  # junto al marco los dedos no bajan más que el marco (más 2 mm de aire)
            z = max(z, z_sup + self.borde_mm_de(lugar) + AIRE_SOBRE_EL_BORDE_MM)
        return (x, y, z, rx, ry, rz + self.giro(perfil))

    def traslado(self, perfil: str) -> float:
        """Cuánto SOBRE la altura de agarre se sube para trasladar: la altura segura, o más si hace falta para que la BASE del objeto pase `holgura_traslado_mm`
        por encima del más alto de los perfiles (`alto_mm`).

        Corrige el error del ajedrez, que restaba el margen de agarre y dejaba la base del objeto `margen` mm más baja de lo pedido.
        """
        segura = float(self.agarre.get("altura_segura_mm", 80.0))
        altos = [float(p["alto_mm"]) for p in self.celda.perfiles.values() if "alto_mm" in p]
        if not altos:
            return segura
        return max(segura, max(altos) + float(self.agarre.get("holgura_traslado_mm", 15.0)))

    def pose_de_agarre(self, lugar: str, perfil: str) -> tuple[float, ...]:
        """En un lugar con desnivel (más bajo que la superficie) la punta baja ese desnivel para tomar el objeto por el mismo punto."""
        return self.pose(lugar, -self._lugar(lugar)[4], perfil)

    def pose_de_soltar(self, lugar: str, perfil: str) -> tuple[float, ...]:
        """Al soltar la punta se queda `elevacion_al_soltar_mm` sobre la altura de agarre; con desnivel, el objeto baja hasta `holgura_cementerio_mm` de la mesa."""
        desnivel = self._lugar(lugar)[4]
        if desnivel > 0:
            return self.pose(lugar, float(self.agarre.get("holgura_cementerio_mm", 2.0)) - desnivel, perfil)
        return self.pose(lugar, float(self.agarre.get("elevacion_al_soltar_mm", 0.0)), perfil)
