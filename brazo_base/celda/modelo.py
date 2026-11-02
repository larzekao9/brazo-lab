"""La celda: el mundo del laboratorio (mesa, puntos, superficies, lugares, objetos y zonas), todo en mm en el sistema de la base del brazo.

Las posiciones `x, y, z` de lugares, superficies y objetos son SIEMPRE del TCP / del objeto en el sistema de la base (el de `brazo.pose()`),
nunca de la brida. `z` de un lugar o superficie es la altura de la superficie sobre la que se apoya la base de un objeto.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from dataclasses import dataclass, field

from brazo_base.errores import CeldaInvalida

HOLGURA_OBJETO_FIJO_MM = 30.0
"""Cuánto se agranda la zona prohibida que genera un objeto no agarrable."""


@dataclass
class Objeto:
    nombre: str
    forma: str  # "caja" | "cilindro"
    posicion: tuple[float, float, float]  # x, y y z de la BASE del objeto
    tamano_mm: tuple[float, float, float] | None = None  # caja: ancho x, ancho y, alto
    radio_mm: float | None = None  # cilindro
    alto_mm: float | None = None  # cilindro
    agarrable: bool = True
    apertura: float = 1.0  # fracción de apertura de la pinza al acercarse (0 a 1)
    agarre_z_mm: float | None = None  # altura sobre la base donde se agarra (por defecto, la mitad)
    modelo_3d: str | None = None
    masa_g: float = 50.0

    @property
    def alto(self) -> float:
        return self.tamano_mm[2] if self.forma == "caja" else float(self.alto_mm)

    @property
    def ancho_agarre_mm(self) -> float:
        """Distancia entre los dedos cuando agarran el objeto."""
        return min(self.tamano_mm[0], self.tamano_mm[1]) if self.forma == "caja" else 2 * float(self.radio_mm)

    @property
    def radio_horizontal_mm(self) -> float:
        return math.hypot(self.tamano_mm[0], self.tamano_mm[1]) / 2 if self.forma == "caja" else float(self.radio_mm)

    @property
    def altura_de_agarre(self) -> float:
        """Cuánto sube el TCP desde la base del objeto al agarrarlo."""
        return self.agarre_z_mm if self.agarre_z_mm is not None else self.alto / 2

    def validar(self) -> None:
        if self.forma not in ("caja", "cilindro"):
            raise CeldaInvalida(f"Objeto «{self.nombre}»: la forma tiene que ser «caja» o «cilindro»")
        if self.forma == "caja" and (not self.tamano_mm or len(self.tamano_mm) != 3 or min(self.tamano_mm) <= 0):
            raise CeldaInvalida(f"Objeto «{self.nombre}»: una caja necesita tamano_mm = [ancho_x, ancho_y, alto] en mm, todos mayores que 0")
        if self.forma == "cilindro" and (not self.radio_mm or not self.alto_mm or self.radio_mm <= 0 or self.alto_mm <= 0):
            raise CeldaInvalida(f"Objeto «{self.nombre}»: un cilindro necesita radio_mm y alto_mm mayores que 0")
        if not 0.0 <= self.apertura <= 1.0:
            raise CeldaInvalida(f"Objeto «{self.nombre}»: apertura va de 0 a 1")


@dataclass
class Superficie:
    """Plano con cuadrícula de `filas` x `columnas`. Un tablero de ajedrez es una superficie 8x8.

    `esquinas` tiene el centro de las casillas extremas: `a1` (fila 0, col 0), `h1` (fila 0, última col), `a8` (última fila, col 0) y, opcional, `h8`.
    Con 3 esquinas la transformación afín (columna, fila) -> (x, y) es exacta; con 4 se ajusta por mínimos cuadrados (igual que el ajedrez), y el
    error de medir cada punto se reparte en vez de acumularse en la esquina que no se midió. Los lugares automáticos son `nombre:<columna><fila>`.

    `z_mm` es la altura de la superficie en el mismo sistema que las poses del brazo (en modo «brida», la z de la brida con las puntas apoyadas).
    `corrimiento_mm` se suma a (x, y) de todo lo que se hace sobre sus casillas (lo medido al centrar la pinza sobre una pieza). `borde_mm` es lo que
    sobresale el marco sobre la superficie: en las casillas del borde nada baja más que `z_mm + borde_mm + 2`.
    """

    nombre: str
    esquinas: dict[str, tuple[float, float]]
    z_mm: float
    filas: int
    columnas: int
    corrimiento_mm: tuple[float, float] = (0.0, 0.0)
    borde_mm: float = 0.0

    def validar(self) -> None:
        faltan = [c for c in ("a1", "h1", "a8") if c not in self.esquinas]
        if faltan:
            raise CeldaInvalida(f"Superficie «{self.nombre}»: faltan las esquinas {', '.join(faltan)} (h8 es opcional)")
        if self.filas < 2 or self.columnas < 2 or self.columnas > 26:
            raise CeldaInvalida(f"Superficie «{self.nombre}»: filas >= 2 y columnas entre 2 y 26")
        ancla = [self._columna_fila(c) for c in self.esquinas]
        if np.linalg.matrix_rank(np.array([[c, f, 1.0] for c, f in ancla])) < 3:
            raise CeldaInvalida(f"Superficie «{self.nombre}»: las esquinas son colineales y no alcanzan para resolver la cuadrícula")

    def _columna_fila(self, esquina: str) -> tuple[int, int]:
        return {"a1": (0, 0), "h1": (self.columnas - 1, 0), "a8": (0, self.filas - 1), "h8": (self.columnas - 1, self.filas - 1)}[esquina]

    def centro(self, columna: int, fila: int) -> tuple[float, float]:
        """Centro de la casilla (columna, fila) contando desde 0 (sin el corrimiento)."""
        nombres = [n for n in ("a1", "h1", "a8", "h8") if n in self.esquinas]
        matriz = np.array([[*self._columna_fila(n), 1.0] for n in nombres])
        cx = np.linalg.lstsq(matriz, np.array([self.esquinas[n][0] for n in nombres]), rcond=None)[0]
        cy = np.linalg.lstsq(matriz, np.array([self.esquinas[n][1] for n in nombres]), rcond=None)[0]
        return float(cx[0] * columna + cx[1] * fila + cx[2]), float(cy[0] * columna + cy[1] * fila + cy[2])

    def _indices(self, texto: str) -> tuple[int, int]:
        texto = texto.strip().lower()
        if len(texto) < 2 or not texto[0].isalpha() or not texto[1:].isdigit():
            raise CeldaInvalida(f"«{texto}» no es una casilla de «{self.nombre}» (usá letra y número, p. ej. a1)")
        columna, fila = ord(texto[0]) - ord("a"), int(texto[1:]) - 1
        if not (0 <= columna < self.columnas and 0 <= fila < self.filas):
            raise CeldaInvalida(f"La casilla «{texto}» no existe en «{self.nombre}» ({self.columnas} columnas x {self.filas} filas)")
        return columna, fila

    def lugar(self, texto: str) -> tuple[float, float, float]:
        """Posición (x, y, z) de una casilla como `e4`, con el corrimiento aplicado."""
        columna, fila = self._indices(texto)
        x, y = self.centro(columna, fila)
        return x + self.corrimiento_mm[0], y + self.corrimiento_mm[1], self.z_mm

    def es_borde(self, texto: str) -> bool:
        """Si la casilla está en la primera o la última fila o columna (junto al marco)."""
        columna, fila = self._indices(texto)
        return columna in (0, self.columnas - 1) or fila in (0, self.filas - 1)


@dataclass
class Celda:
    nombre: str = "Celda sin nombre"
    version: int = 1
    controlador: dict = field(default_factory=lambda: {"host": "192.168.5.1", "puerto": 29999})
    herramienta: str = "ninguna"
    herramienta_config: dict = field(default_factory=dict)
    seguridad: dict = field(default_factory=lambda: {"velocidad_maxima_real": 50, "limites_mesa": None, "altura_minima_mm": 5, "altura_segura_mm": 150})
    mesa: dict = field(default_factory=lambda: {"z_mm": 0.0})
    puntos: dict[str, dict] = field(default_factory=dict)
    superficies: dict[str, Superficie] = field(default_factory=dict)
    lugares: dict[str, dict] = field(default_factory=dict)
    objetos: dict[str, Objeto] = field(default_factory=dict)
    zonas_prohibidas: list[dict] = field(default_factory=list)
    modo_pose: str = "tcp"
    """`"tcp"`: las poses que ve el estudiante son las de la punta, con la herramienta vertical. `"brida"`: son las de la brida con la orientación enseñada
    (`orientacion`), tal cual las lee y las manda el controlador: así funcionó el ajedrez en el laboratorio, hasta definir la herramienta en el controlador."""
    orientacion: tuple[float, float, float] | None = None
    """`(rx, ry, rz)` de la herramienta con la pinza apuntando a la mesa, tomada de `GetPose()` (la del punto a1 enseñado)."""
    agarre: dict = field(default_factory=dict)
    """Valores comunes del pick and place por perfiles (ver `docs/conceptos.md`): `altura_segura_mm`, `holgura_traslado_mm`, `velocidad_bajada`…"""
    perfiles: dict[str, dict] = field(default_factory=dict)
    """Perfiles de agarre por tipo de objeto: `margen_mm`, `apertura` (0 a 1), `giro_grados`, `alto_mm`."""
    avisos: list[str] = field(default_factory=list)
    ruta: str | None = None

    # --- lo que lee el módulo de zonas (`problemas_de_punto` mira estos dos nombres) ---------------------------------
    @property
    def limites_mesa(self) -> list[float] | None:
        return self.seguridad.get("limites_mesa")

    @property
    def zonas_efectivas(self) -> list[dict]:
        """Las zonas escritas a mano más una por cada objeto fijo (no agarrable), con holgura."""
        zonas = list(self.zonas_prohibidas)
        for o in self.objetos.values():
            if not o.agarrable:
                x, y, z = o.posicion
                zonas.append({"nombre": o.nombre, "forma": "circulo", "x": x, "y": y, "radio": o.radio_horizontal_mm + HOLGURA_OBJETO_FIJO_MM, "z_min": None, "z_max": z + o.alto})
        return zonas

    @property
    def altura_minima_mm(self) -> float:
        return float(self.seguridad.get("altura_minima_mm", 5))

    @property
    def altura_segura_mm(self) -> float:
        return float(self.seguridad.get("altura_segura_mm", 150))

    @property
    def largo_herramienta_mm(self) -> float:
        return float(self.herramienta_config.get("largo_mm", 0.0))

    @property
    def mesa_z_mm(self) -> float:
        return float(self.mesa.get("z_mm", 0.0))

    def copia(self) -> "Celda":
        return copy.deepcopy(self)

    # --- lugares ---------------------------------------------------------------------------------------------------------
    def posicion_de(self, nombre: str, posiciones_objetos: dict[str, tuple[float, float, float]] | None = None) -> tuple[float, float, float]:
        """(x, y, z) de un lugar con nombre: lugar fijo, `superficie:casilla` u objeto (donde está ahora). `z` es la altura de la superficie donde
        se apoya algo: para un objeto, su tope (así `soltar_en("caja_roja")` apila encima)."""
        posiciones = posiciones_objetos or {o.nombre: o.posicion for o in self.objetos.values()}
        if ":" in nombre:
            sup, casilla = nombre.split(":", 1)
            if sup not in self.superficies:
                raise CeldaInvalida(f"No hay una superficie «{sup}» en la celda. Superficies: {', '.join(self.superficies) or 'ninguna'}")
            return self.superficies[sup].lugar(casilla)
        if nombre in self.lugares:
            lugar = self.lugares[nombre]
            if "objeto" in lugar:
                return self.posicion_de(lugar["objeto"], posiciones)
            return float(lugar["x"]), float(lugar["y"]), float(lugar.get("z", self.mesa_z_mm))
        if nombre in posiciones:
            x, y, z = (float(v) for v in posiciones[nombre])
            return x, y, z + (self.objetos[nombre].alto if nombre in self.objetos else 0.0)
        conocidos = sorted({*self.lugares, *self.objetos})
        raise CeldaInvalida(f"No conozco el lugar «{nombre}». Lugares y objetos de la celda: {', '.join(conocidos) or 'ninguno'}")

    def validar(self) -> None:
        for o in self.objetos.values():
            o.validar()
        for s in self.superficies.values():
            s.validar()
        if self.limites_mesa is not None:
            from brazo_base.seguridad import zonas

            try:
                self.seguridad["limites_mesa"] = zonas.validar_limites(self.limites_mesa)
                zonas.validar_zonas(self.zonas_prohibidas)
            except ValueError as error:
                raise CeldaInvalida(str(error)) from error
        else:
            from brazo_base.seguridad import zonas

            try:
                zonas.validar_zonas(self.zonas_prohibidas)
            except ValueError as error:
                raise CeldaInvalida(str(error)) from error
