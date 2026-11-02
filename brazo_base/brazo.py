"""La clase `Brazo`: lo único que tiene que conocer un estudiante.

    from brazo_base import Brazo
    with Brazo() as brazo:                      # simulador por defecto
        brazo.llevar("caja_roja", "bandeja")

El mismo código corre contra el brazo real con `Brazo(destino="real", celda="celda/celda.json")`. Las poses están SIEMPRE en el TCP (la punta de la
herramienta), con la herramienta vertical; la plataforma le suma el largo de la herramienta para hablarle al controlador (que usa la brida).
"""
from __future__ import annotations

import math
import time
from pathlib import Path

from brazo_base.celda import Celda, cargar_celda, celda_demo
from brazo_base.conexion.cliente_dobot import MODO_LIBRE, ClienteDobot, ErrorDobot
from brazo_base.errores import ErrorBrazo, ErrorDelControlador, NoAgarro, NoHabilitado, RecorridoProhibido, SinConexion
from brazo_base.herramientas import herramienta_desde_config
from brazo_base.seguridad import trayectos, validador
from brazo_base.seguridad.validador import Tramo

VELOCIDAD_REAL_POR_DEFECTO = 20
VELOCIDAD_SIMULADOR_POR_DEFECTO = 60
ESPERA_ENCENDIDO_S = 20.0
MARGEN_SOLTAR_MM = 1.0
"""Cuánto por encima de la superficie se suelta (la base queda a esta distancia al abrir)."""


class Brazo:
    def __init__(self, destino: str = "simulador", celda: Celda | str | Path | None = None, velocidad: int | None = None, velocidad_simulacion: float = 1.0):
        """
        Args:
            destino: `"simulador"` (por defecto, nunca toca el brazo) o `"real"` (exige pasar la celda del laboratorio).
            celda: una `Celda`, la ruta a un `celda.json`, o `None` para la celda de práctica (solo simulador).
            velocidad: porcentaje de velocidad (1 a 100). Real: 20 por defecto y con tope en `seguridad.velocidad_maxima_real` de la celda.
            velocidad_simulacion: cuántas veces más rápido que el tiempo real corre el simulador.
        """
        if destino not in ("simulador", "real"):
            raise ErrorBrazo(f"destino tiene que ser «simulador» o «real», no «{destino}»")
        self.destino = destino
        if celda is None:
            if destino == "real":
                raise ErrorBrazo("Para el brazo real pasá la celda del laboratorio: Brazo(destino='real', celda='celda/celda.json')")
            celda = celda_demo()
        elif not isinstance(celda, Celda):
            celda = cargar_celda(celda)
        self.celda: Celda = celda
        self.herramienta = herramienta_desde_config(celda.herramienta_config, celda.herramienta)
        base = VELOCIDAD_SIMULADOR_POR_DEFECTO if destino == "simulador" else VELOCIDAD_REAL_POR_DEFECTO
        v = base if velocidad is None else int(velocidad)
        if not 1 <= v <= 100:
            raise ErrorBrazo("La velocidad va de 1 a 100 (%)")
        if destino == "real":
            v = min(v, int(celda.seguridad.get("velocidad_maxima_real", 50)))
        self.velocidad = v
        self.velocidad_simulacion = velocidad_simulacion
        self.simulador = None
        self._servidor = None
        self._cliente: ClienteDobot | None = None
        self._habilitado = False
        self._sostiene: str | None = None
        self._posiciones = {n: tuple(o.posicion) for n, o in celda.objetos.items()}

    # --- conexión -----------------------------------------------------------------------------------------------------------
    def conectar(self) -> None:
        """Real: se conecta al controlador, NO habilita. Simulador: levanta el controlador virtual y se conecta a él con el mismo cliente."""
        if self._cliente is not None:
            return
        host, puerto = self.celda.controlador.get("host", "192.168.5.1"), int(self.celda.controlador.get("puerto", 29999))
        if self.destino == "simulador":
            from brazo_base.simulador.nucleo import Simulador
            from brazo_base.simulador.protocolo import ProtocoloDobot
            from brazo_base.simulador.servidor_tcp import ServidorDashboard

            self.simulador = Simulador(self.celda, escala_tiempo=self.velocidad_simulacion)
            self._servidor = ServidorDashboard(ProtocoloDobot(self.simulador), "127.0.0.1", 0)
            self._servidor.iniciar()
            host, puerto = "127.0.0.1", self._servidor.puerto
        cliente = ClienteDobot(host, puerto, velocidad_global=self.velocidad, velocidad=self.velocidad)
        try:
            cliente.conectar()
        except (ErrorDobot, OSError) as error:
            self._cerrar_servidor()
            raise ErrorBrazo(f"No se pudo conectar con el controlador en {host}:{puerto}: {error}") from error
        self._cliente = cliente

    def habilitar(self) -> None:
        """Enciende (si hace falta) y habilita el brazo; deja lista la herramienta. En el brazo real se mueve de verdad después de esto."""
        c = self._exigir_conexion()
        try:
            modo = c.modo()
            if modo == 3:
                c.enviar("PowerOn()")
                self._esperar(lambda: c.modo() != 3, "El brazo no terminó de encenderse")
                modo = c.modo()
            if modo == 4:
                c.enviar("EnableRobot()")
                self._esperar(lambda: c.modo() == MODO_LIBRE, "El brazo no terminó de habilitarse")
            elif modo != MODO_LIBRE and modo not in (6, 7, 8):
                raise ErrorDelControlador(f"El brazo está en el modo {modo}: resolvé la alarma (brazo.limpiar_error()) antes de habilitar")
            self.herramienta.conectar(c)
            self._habilitado = True
            if self.destino == "simulador":
                self.herramienta.inicializar()
        except ErrorDobot as error:
            raise ErrorDelControlador(str(error)) from error

    def _esperar(self, condicion, mensaje: str) -> None:
        fin = time.monotonic() + ESPERA_ENCENDIDO_S
        while time.monotonic() < fin:
            if condicion():
                return
            time.sleep(0.1)
        raise ErrorDelControlador(mensaje)

    def limpiar_error(self) -> None:
        self._exigir_conexion().enviar("ClearError()")

    def parar(self) -> None:
        """Frena y cancela lo que esté en curso (funciona desde otro hilo). El siguiente movimiento que se pida vuelve a andar."""
        if self._cliente is not None:
            self._cliente.cancelar()

    def desconectar(self) -> None:
        """Cierra la conexión. El brazo NO se deshabilita (frenaría de golpe)."""
        try:
            if self._cliente is not None:
                self.herramienta.desconectar()
                self._cliente.cerrar()
        finally:
            self._cliente, self._habilitado = None, False
            self._cerrar_servidor()

    def _cerrar_servidor(self) -> None:
        if self._servidor is not None:
            self._servidor.detener()
            self._servidor = None
        if self.simulador is not None:
            self.simulador.apagar()
            self.simulador = None

    def __enter__(self) -> "Brazo":
        self.conectar()
        if self.destino == "simulador":
            self.habilitar()
        return self

    def __exit__(self, *args) -> None:
        self.desconectar()

    def _exigir_conexion(self) -> ClienteDobot:
        if self._cliente is None:
            raise SinConexion("El brazo no está conectado: llamá a brazo.conectar() primero (o usá «with Brazo() as brazo:»)")
        return self._cliente

    def _listo(self) -> ClienteDobot:
        c = self._exigir_conexion()
        if not self._habilitado:
            raise NoHabilitado("El brazo está conectado pero no habilitado: llamá a brazo.habilitar() antes de mover")
        c.reanudar()
        return c

    # --- lectura --------------------------------------------------------------------------------------------------------------
    @property
    def largo_mm(self) -> float:
        return float(self.herramienta.largo_mm)

    def pose(self) -> tuple[float, float, float, float, float, float]:
        """`(x, y, z, rx, ry, rz)` del TCP, en mm y grados."""
        x, y, z, rx, ry, rz = self._exigir_conexion().pose()
        return (x, y, z - self.largo_mm, rx, ry, rz)

    def angulos(self) -> tuple[float, ...]:
        return self._exigir_conexion().angulos()

    def estado(self) -> dict:
        c = self._exigir_conexion()
        try:
            return {"destino": self.destino, "habilitado": self._habilitado, "modo": c.modo(), "pose": self.pose(), "angulos": self.angulos(),
                    "herramienta": self.herramienta.estado() if self._habilitado else {"herramienta": self.herramienta.nombre},
                    "sostiene": self._sostiene}
        except ErrorDobot as error:
            raise ErrorDelControlador(str(error)) from error

    # --- movimiento -----------------------------------------------------------------------------------------------------------
    def _a_brida(self, x: float, y: float, z: float, rz: float) -> tuple[float, float, float, float, float, float]:
        return (x, y, z + self.largo_mm, 180.0, 0.0, rz)

    def _ejecutar(self, accion):
        try:
            return accion()
        except ErrorDobot as error:
            raise ErrorDelControlador(str(error)) from error
        except TimeoutError as error:
            raise ErrorDelControlador(str(error)) from error

    def mover_a(self, x: float | None = None, y: float | None = None, z: float | None = None, rz: float | None = None, lineal: bool = True) -> None:
        """Lleva el TCP a `(x, y, z)` mm con la herramienta vertical. Lo que no se da se queda como está. Valida el recorrido antes de mover."""
        c = self._listo()
        ax, ay, az, _, _, arz = self.pose()
        destino = (ax if x is None else x, ay if y is None else y, az if z is None else z)
        validador.exigir_tramos([Tramo((ax, ay, az), destino, "mover_a")], self.celda)
        self._ir(c, destino, arz if rz is None else rz, lineal)

    def _ir(self, c: ClienteDobot, destino: tuple[float, float, float], rz: float, lineal: bool = True) -> None:
        self._ejecutar(lambda: c.mover_a_pose(self._a_brida(*destino, rz), lineal=lineal))

    def mover_relativo(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        x, y, z, *_ = self.pose()
        self.mover_a(x + dx, y + dy, z + dz)

    def mover_articulaciones(self, angulos: list[float] | tuple[float, ...]) -> None:
        """Va a los 6 ángulos (grados). Valida límites de articulación, mesa, choques entre eslabones y zonas con TODO el brazo."""
        c = self._listo()
        validador.exigir_articulaciones(list(self.angulos()), list(angulos), self.celda)
        self._ejecutar(lambda: c.mover_a_angulos(tuple(angulos)))

    def ir_a(self, nombre: str) -> None:
        """Va a un punto con nombre (`puntos` de la celda: por ángulos, o por pose de la brida) o a un lugar (arriba del lugar, a la altura segura)."""
        punto = self.celda.puntos.get(nombre)
        if punto is not None:
            if "angulos" in punto:
                return self.mover_articulaciones(punto["angulos"])
            if "pose" in punto:
                x, y, zb, _, _, rz = punto["pose"]
                return self.mover_a(x, y, zb - self.largo_mm, rz)
            raise ErrorBrazo(f"El punto «{nombre}» no tiene ni «angulos» ni «pose»")
        x, y, _ = self.celda.posicion_de(nombre, self._posiciones)
        self._subir_y_ir(x, y, self.celda.altura_segura_mm)

    def _subir_y_ir(self, x: float, y: float, z_viaje: float) -> None:
        z = max(self.pose()[2], z_viaje)
        self.mover_a(z=z)
        self.mover_a(x, y, z)

    # --- herramienta (atajos con las comprobaciones de brazo habilitado) -------------------------------------------------------
    def _herramienta(self):
        self._listo()
        return self.herramienta

    # --- pick and place -----------------------------------------------------------------------------------------------------------
    def _plan_agarrar(self, nombre: str) -> tuple[list[tuple[str, tuple]], list[Tramo]]:
        o = self.celda.objetos.get(nombre)
        if o is None:
            raise ErrorBrazo(f"No hay un objeto «{nombre}» en la celda. Objetos: {', '.join(self.celda.objetos) or 'ninguno'}")
        if not o.agarrable:
            raise ErrorBrazo(f"El objeto «{nombre}» no es agarrable (está marcado como fijo en la celda)")
        carrera = getattr(self.herramienta, "carrera_mm", None)
        if carrera is not None:
            if o.ancho_agarre_mm > carrera:
                raise ErrorBrazo(f"«{nombre}» mide {o.ancho_agarre_mm:.0f} mm de ancho y la pinza abre como máximo {carrera:.0f} mm: no cabe")
            if o.apertura * carrera < o.ancho_agarre_mm:
                raise ErrorBrazo(f"Con apertura={o.apertura} la pinza abre {o.apertura * carrera:.1f} mm y «{nombre}» mide {o.ancho_agarre_mm:.0f} mm: subí «apertura» del objeto en la celda")
        ox, oy, oz = self._posiciones[nombre]
        z_agarre = oz + o.altura_de_agarre
        z_viaje = trayectos.altura_de_traslado(self.celda, trayectos.alto_maximo_de_objetos(self.celda, excepto=nombre))
        ax, ay, az, *_ = self.pose()
        z_alto = max(az, z_viaje)
        pasos = [("abrir", (o.apertura,)), ("mover", (ax, ay, z_alto)), ("mover", (ox, oy, z_alto)), ("mover", (ox, oy, z_agarre)), ("cerrar", ()), ("mover", (ox, oy, z_alto))]
        puntos = [(ax, ay, az)] + [p[1] for p in pasos if p[0] == "mover"]
        tramos = [Tramo(a, b, f"agarrar {nombre}") for a, b in zip(puntos, puntos[1:])]
        return pasos, tramos

    def agarrar(self, nombre: str) -> None:
        """Abre, baja sobre el objeto, cierra, comprueba que lo sostiene y sube. Valida todo el recorrido antes de mover."""
        c = self._listo()
        if self._sostiene:
            raise NoAgarro(f"Ya estás sosteniendo «{self._sostiene}»: soltalo antes con soltar_en()")
        pasos, tramos = self._plan_agarrar(nombre)
        validador.exigir_tramos(tramos, self.celda)
        rz = self.pose()[5]
        for tipo, args in pasos:
            if tipo == "abrir":
                self.herramienta.abrir_a(args[0])
            elif tipo == "mover":
                self._ir(c, args, rz)
            elif tipo == "cerrar":
                sostiene = self.herramienta.cerrar()
                if sostiene is False:
                    self.herramienta.abrir()
                    self._ir(c, (self.pose()[0], self.pose()[1], pasos[1][1][2]), rz)
                    raise NoAgarro(f"La herramienta cerró y no sostiene nada: «{nombre}» no estaba donde la celda dice. Revisá su posición o el ancho de apertura")
        estado = self.herramienta.estado()
        if estado.get("sostiene") is False:
            raise NoAgarro(f"«{nombre}» se cayó al subir. Probá con más fuerza o una apertura menor")
        self._sostiene = nombre

    def soltar_en(self, lugar: str) -> None:
        """Va arriba del lugar, baja hasta apoyar la base del objeto, abre y sube."""
        c = self._listo()
        if not self._sostiene:
            raise NoAgarro("No estás sosteniendo nada: usá agarrar() primero")
        nombre = self._sostiene
        o = self.celda.objetos[nombre]
        lx, ly, lz = self.celda.posicion_de(lugar, {n: p for n, p in self._posiciones.items() if n != nombre})
        z_viaje = trayectos.altura_de_traslado(self.celda, trayectos.alto_maximo_de_objetos(self.celda, excepto=nombre), o.altura_de_agarre)
        z_suelta = lz + o.altura_de_agarre + MARGEN_SOLTAR_MM
        ax, ay, az, *_ = self.pose()
        z_alto = max(az, z_viaje)
        puntos = [(ax, ay, az), (ax, ay, z_alto), (lx, ly, z_alto), (lx, ly, z_suelta), (lx, ly, z_alto)]
        validador.exigir_tramos([Tramo(a, b, f"soltar {nombre} en {lugar}") for a, b in zip(puntos, puntos[1:])], self.celda)
        rz = self.pose()[5]
        self._ir(c, puntos[1], rz)
        self._ir(c, puntos[2], rz)
        self._ir(c, puntos[3], rz)
        self.herramienta.abrir_a(o.apertura)
        self._posiciones[nombre] = (lx, ly, lz)
        self._sostiene = None
        self._ir(c, puntos[4], rz)

    def _tramos_llevar(self, objeto: str, lugar: str) -> list[Tramo]:
        """Todos los tramos de punta de `llevar` (agarrar + trasladar + soltar), sin mover nada."""
        _, tramos_agarrar = self._plan_agarrar(objeto)
        o = self.celda.objetos[objeto]
        lx, ly, lz = self.celda.posicion_de(lugar, {n: p for n, p in self._posiciones.items() if n != objeto})
        ox, oy, _ = self._posiciones[objeto]
        otros = trayectos.alto_maximo_de_objetos(self.celda, excepto=objeto)
        z_viaje = trayectos.altura_de_traslado(self.celda, otros, o.altura_de_agarre)
        z_ini = max(self.pose()[2], trayectos.altura_de_traslado(self.celda, otros))
        z_suelta = lz + o.altura_de_agarre + MARGEN_SOLTAR_MM
        return tramos_agarrar + [Tramo((ox, oy, z_ini), (ox, oy, z_viaje), "llevar"), Tramo((ox, oy, z_viaje), (lx, ly, z_viaje), "llevar"), Tramo((lx, ly, z_viaje), (lx, ly, z_suelta), "llevar")]

    def llevar(self, objeto: str, lugar: str) -> None:
        """`agarrar` y `soltar_en`. Antes de mover nada comprueba que el recorrido completo (también el de soltar) es válido."""
        self._listo()
        validador.exigir_tramos(self._tramos_llevar(objeto, lugar), self.celda)
        self.agarrar(objeto)
        self.soltar_en(lugar)

    def ensayo(self, tipo: str, **datos) -> dict:
        """Lo que haría `mover_a` / `llevar` / `mover_articulaciones` SIN mover nada: `{"ok", "problemas", "tramos"}`."""
        self._exigir_conexion()
        tramos: list[Tramo] = []
        if tipo == "mover":
            ax, ay, az, *_ = self.pose()
            destino = tuple(datos.get(k, a) if datos.get(k) is not None else a for k, a in zip("xyz", (ax, ay, az)))
            tramos = [Tramo((ax, ay, az), destino, "mover_a")]
        elif tipo == "llevar":
            tramos = self._tramos_llevar(datos["objeto"], datos["lugar"])
        elif tipo == "articulaciones":
            try:
                validador.exigir_articulaciones(list(self.angulos()), list(datos["angulos"]), self.celda)
                problemas: list[str] = []
            except RecorridoProhibido as error:
                problemas = error.problemas
            return {"ok": not problemas, "problemas": problemas, "tramos": []}
        else:
            raise ErrorBrazo(f"Ensayo desconocido «{tipo}»: usá mover, llevar o articulaciones")
        problemas = validador.problemas_de_tramos(tramos, self.celda)
        return {"ok": not problemas, "problemas": problemas, "tramos": [{"desde": t.desde, "hasta": t.hasta} for t in tramos]}

    @property
    def sostiene(self) -> str | None:
        return self._sostiene

    def posiciones_objetos(self) -> dict[str, tuple[float, float, float]]:
        """Dónde está cada objeto ahora (en el simulador, lo que dice el mundo; en el real, lo que la celda supone)."""
        if self.simulador is not None:
            return {n: tuple(p) for n, p in self.simulador.mundo.posiciones().items()}
        return dict(self._posiciones)

    def ejecutar_rutina(self, nombre: str) -> None:
        raise NotImplementedError("Las rutinas llegan en la fase 3 (ver docs/bitacora.md)")
