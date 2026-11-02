"""La pinza DH PGE-50-26 simulada: registros Modbus y estado de agarre que salen de lo que pasa en el mundo físico."""
from __future__ import annotations

from brazo_base.herramientas import pinza_dh
from brazo_base.simulador.parametros import ParametrosFisicos

REGISTROS_CONOCIDOS = (
    pinza_dh.REG_INICIALIZAR,
    pinza_dh.REG_FUERZA,
    0x0102,
    pinza_dh.REG_POSICION,
    pinza_dh.REG_VELOCIDAD,
    pinza_dh.REG_ESTADO_INICIALIZACION,
    pinza_dh.REG_ESTADO_AGARRE,
    pinza_dh.REG_POSICION_ACTUAL,
)
MARGEN_LLEGADA_MM = 0.4
PASOS_SIN_CONTACTO_PARA_CAIDA = 24


class PinzaSimulada:
    """Estado de la pinza. `actualizar` se llama una vez por paso de física; `leer` y `escribir` son los registros Modbus."""

    def __init__(self, mundo, fisicos: ParametrosFisicos, registrar):
        self.mundo, self.fisicos, self._registrar = mundo, fisicos, registrar
        self.inicializada = False
        self.fuerza_pct, self.velocidad_pct = 100, 100
        self.posicion_objetivo = 1000
        self.agarre = pinza_dh.AGARRE_LLEGO
        self.ancho_mm = fisicos.carrera_mm
        self.fuerza_contacto_n = 0.0
        self._agarre_visible = pinza_dh.AGARRE_LLEGO
        self._agarre_visible_anterior = pinza_dh.AGARRE_LLEGO
        self._tiempo_orden = -1e9
        self._fin_inicializacion: float | None = None
        self._inicio_inicializacion = 0.0
        self._duracion_inicializacion = 0.0
        self._pasos_sin_contacto = 0
        self._tuvo_objeto = False
        self.tiempo = 0.0

    # --- registros -----------------------------------------------------------------------------------------------------
    @property
    def posicion_actual(self) -> int:
        return max(0, min(1000, round(self.ancho_mm / self.fisicos.carrera_mm * 1000)))

    def leer(self, direccion: int) -> int | None:
        """Valor del registro, o `None` si la pinza no tiene ese registro."""
        valores = {
            pinza_dh.REG_INICIALIZAR: 1 if self.inicializada else 0,
            pinza_dh.REG_FUERZA: self.fuerza_pct,
            0x0102: 0,
            pinza_dh.REG_POSICION: self.posicion_objetivo,
            pinza_dh.REG_VELOCIDAD: self.velocidad_pct,
            pinza_dh.REG_ESTADO_INICIALIZACION: 1 if self.inicializada else 0,
            pinza_dh.REG_ESTADO_AGARRE: self._agarre_visible,
            pinza_dh.REG_POSICION_ACTUAL: self.posicion_actual,
        }
        return valores.get(direccion)

    def escribir(self, direccion: int, valor: int) -> bool:
        """Escribe un registro; `False` si la pinza no tiene ese registro."""
        if direccion not in REGISTROS_CONOCIDOS:
            return False
        if direccion == pinza_dh.REG_INICIALIZAR:
            if valor in (1, 0xA5):
                self._iniciar_inicializacion(recalibrar=valor == 0xA5)
        elif direccion == pinza_dh.REG_FUERZA:
            self.fuerza_pct = max(20, min(100, valor))
            self._aplicar_dedos()
        elif direccion == pinza_dh.REG_VELOCIDAD:
            self.velocidad_pct = max(1, min(100, valor))
            self._aplicar_dedos()
        elif direccion == pinza_dh.REG_POSICION:
            if not self.inicializada:
                self._registrar("pinza", f"posición {valor} ignorada: la pinza no está inicializada")
            else:
                self._ordenar_posicion(max(0, min(1000, valor)))
        return True

    # --- comportamiento ------------------------------------------------------------------------------------------------
    def _fuerza_total_n(self) -> float:
        f = self.fisicos
        return f.fuerza_total_min_n + (f.fuerza_total_max_n - f.fuerza_total_min_n) * (self.fuerza_pct - 20) / 80

    def _velocidad_mm_s(self) -> float:
        return self.fisicos.velocidad_dedos_max_mm_s * self.velocidad_pct / 100

    def _aplicar_dedos(self) -> None:
        self.mundo.fijar_dedos(self.posicion_objetivo / 1000 * self.fisicos.carrera_mm, self._fuerza_total_n(), self._velocidad_mm_s())

    def _ordenar_posicion(self, posicion: int) -> None:
        self._agarre_visible_anterior = self._agarre_visible
        self.posicion_objetivo = posicion
        self._tiempo_orden = self.tiempo
        self._pasos_sin_contacto = 0
        self._tuvo_objeto = False
        llego = abs(self.ancho_mm - posicion / 1000 * self.fisicos.carrera_mm) <= MARGEN_LLEGADA_MM
        self.agarre = pinza_dh.AGARRE_LLEGO if llego else pinza_dh.AGARRE_EN_MOVIMIENTO
        self._aplicar_dedos()

    def _iniciar_inicializacion(self, recalibrar: bool) -> None:
        self.inicializada = False
        self._inicio_inicializacion = self.tiempo
        self._duracion_inicializacion = self.fisicos.duracion_recalibracion_s if recalibrar else self.fisicos.duracion_inicializacion_s
        self._fin_inicializacion = self.tiempo + self._duracion_inicializacion
        self.mundo.fijar_dedos(0.0, self._fuerza_total_n(), self.fisicos.velocidad_dedos_max_mm_s)
        self._registrar("pinza", "inicializando" + (" (recalibración)" if recalibrar else ""))

    def _actualizar_inicializacion(self) -> None:
        if self._fin_inicializacion is None:
            return
        mitad = self._inicio_inicializacion + self._duracion_inicializacion / 2
        if self.tiempo < mitad:
            return
        if self.tiempo < self._fin_inicializacion:
            self.mundo.fijar_dedos(self.fisicos.carrera_mm, self._fuerza_total_n(), self.fisicos.velocidad_dedos_max_mm_s)
            return
        self._fin_inicializacion = None
        self.inicializada = True
        self.fuerza_pct, self.velocidad_pct, self.posicion_objetivo = 100, 100, 1000
        self.agarre = pinza_dh.AGARRE_LLEGO
        self._agarre_visible = self._agarre_visible_anterior = pinza_dh.AGARRE_LLEGO
        self._aplicar_dedos()
        self._registrar("pinza", "inicializada (fuerza y velocidad vuelven a 100 %)")

    def actualizar(self, tiempo: float) -> None:
        """Calcula el estado de agarre a partir de los dedos y los contactos del mundo, y lo publica con la latencia del real."""
        self.tiempo = tiempo
        self._actualizar_inicializacion()
        self.ancho_mm, velocidad = self.mundo.estado_dedos()
        self.fuerza_contacto_n = self.mundo.fuerza_de_contacto_con_piezas_n()
        if self._fin_inicializacion is not None:
            return
        objetivo_mm = self.posicion_objetivo / 1000 * self.fisicos.carrera_mm
        contacto = self.fuerza_contacto_n > self.fisicos.umbral_contacto_n
        self._pasos_sin_contacto = 0 if contacto else self._pasos_sin_contacto + 1
        if tiempo - self._tiempo_orden >= 0.1 and self.agarre != pinza_dh.AGARRE_SE_CAYO:
            llego = abs(self.ancho_mm - objetivo_mm) <= MARGEN_LLEGADA_MM
            quieto = abs(velocidad) < 1.5
            cerrando = objetivo_mm < self.ancho_mm - MARGEN_LLEGADA_MM
            if self._tuvo_objeto and (llego or self._pasos_sin_contacto > PASOS_SIN_CONTACTO_PARA_CAIDA):
                self.agarre = pinza_dh.AGARRE_SE_CAYO
                self._registrar("pinza", "agarre 3: se perdió la pieza que sostenía")
            elif llego:
                self.agarre = pinza_dh.AGARRE_LLEGO
            elif quieto and cerrando and contacto:
                self.agarre = pinza_dh.AGARRE_SOSTIENE
                self._tuvo_objeto = True
            elif not self._tuvo_objeto:
                self.agarre = pinza_dh.AGARRE_EN_MOVIMIENTO
        if tiempo - self._tiempo_orden >= self.fisicos.latencia_estado_pinza_s:
            self._agarre_visible = self.agarre
