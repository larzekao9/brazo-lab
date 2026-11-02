"""Protocolo del dashboard del Dobot (texto por TCP): analiza cada comando, lo ejecuta contra el `Simulador` y arma `ErrorID,{valores},Comando(...);`.

Comandos soportados: ver `COMANDOS`. Lo que no está ahí responde `-10000` (no existe); con un número de parámetros incorrecto, `-20000`.
Los comandos Modbus (`SetTool485`, `ModbusCreate`, `ModbusClose`, `GetHoldRegs`, `SetHoldRegs`) emulan el canal interno hacia la pinza
(`127.0.0.1:60000`), que en el controlador real no sale por la red.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from brazo_base.simulador.nucleo import ErrorDeComando, Simulador

PATRON_COMANDO = re.compile(r"^\s*(\w+)\s*\((.*)\)\s*$", re.S)
TEXTO_SIN_CONTROL_TCP = "Control Mode Is Not Tcp;"


@dataclass
class SesionDashboard:
    """Lo que pertenece a una conexión TCP: sus maestros Modbus abiertos."""

    maestros: set[int] = field(default_factory=set)


def separar_comandos(buffer: str) -> tuple[list[str], str]:
    """Corta `buffer` en comandos completos (paréntesis balanceados) y devuelve `(comandos, resto sin terminar)`."""
    comandos, profundidad, inicio = [], 0, 0
    for posicion, caracter in enumerate(buffer):
        if caracter == "(":
            profundidad += 1
        elif caracter == ")":
            profundidad -= 1
            if profundidad == 0:
                comandos.append(buffer[inicio : posicion + 1].strip())
                inicio = posicion + 1
    return comandos, buffer[inicio:]


def separar_parametros(texto: str) -> list[str]:
    """Parte `a,{1,2},c=3` en `['a', '{1,2}', 'c=3']` respetando llaves y comillas."""
    partes, actual, llaves, comillas = [], "", 0, False
    for caracter in texto:
        if caracter == '"':
            comillas = not comillas
        elif not comillas and caracter == "{":
            llaves += 1
        elif not comillas and caracter == "}":
            llaves -= 1
        if caracter == "," and llaves == 0 and not comillas:
            partes.append(actual.strip())
            actual = ""
        else:
            actual += caracter
    if actual.strip() or partes:
        partes.append(actual.strip())
    return partes


def _numeros(texto: str) -> tuple[float, ...]:
    return tuple(float(v) for v in texto.strip().strip("{}").split(",") if v.strip())


def _formato(valores) -> str:
    return ",".join(f"{v:.6f}" for v in valores)


class ProtocoloDobot:
    """Intérprete de comandos; una instancia por simulador, `procesar` es seguro entre hilos."""

    def __init__(self, simulador: Simulador):
        self.simulador = simulador
        self.maestros: dict[int, tuple[int]] = {}
        self.tool485_configurado = False
        self._siguiente_maestro = 0

    # --- entrada --------------------------------------------------------------------------------------------------------
    def procesar(self, comando: str, sesion: SesionDashboard) -> str:
        """Respuesta completa (termina en `;`) a un comando."""
        sim = self.simulador
        sim.registrar("->", comando)
        try:
            respuesta = self._responder(comando, sesion)
        except ErrorDeComando as error:
            if error.motivo:
                sim.registrar("sim", f"{comando.split('(')[0]} rechazado: {error.motivo}")
            respuesta = f"{error.codigo},{{}},{comando};"
        sim.registrar("<-", respuesta)
        return respuesta

    def _responder(self, comando: str, sesion: SesionDashboard) -> str:
        sim = self.simulador
        coincidencia = PATRON_COMANDO.match(comando)
        if not coincidencia:
            raise ErrorDeComando(-10000)
        nombre, crudo = coincidencia.group(1), coincidencia.group(2)
        manejador = self.COMANDOS.get(nombre.lower())
        if manejador is None:
            raise ErrorDeComando(-10000)
        with sim.cerrojo:
            if sim.fallos.no_tcp and nombre.lower() != "requestcontrol":
                return TEXTO_SIN_CONTROL_TCP
            valores = manejador(self, separar_parametros(crudo), sesion)
        return f"0,{{{valores}}},{comando};"

    def cerrar_sesion(self, sesion: SesionDashboard) -> None:
        """Libera los maestros Modbus que dejó abiertos una conexión que se cayó."""
        for maestro in list(sesion.maestros):
            self.maestros.pop(maestro, None)
        sesion.maestros.clear()

    # --- ayudas -----------------------------------------------------------------------------------------------------------
    @staticmethod
    def _exigir(parametros: list[str], minimo: int, maximo: int | None = None) -> None:
        if not minimo <= len(parametros) <= (maximo if maximo is not None else minimo):
            raise ErrorDeComando(-20000)

    @staticmethod
    def _opciones(parametros: list[str]) -> dict[str, float]:
        opciones = {}
        for parametro in parametros:
            if "=" in parametro and not parametro.startswith(("pose", "joint")):
                clave, valor = parametro.split("=", 1)
                try:
                    opciones[clave.strip().lower()] = float(valor)
                except ValueError:
                    raise ErrorDeComando(-50001) from None
        return opciones

    def _punto(self, parametros: list[str]) -> tuple[str, tuple[float, ...]]:
        if not parametros:
            raise ErrorDeComando(-20000)
        primero = parametros[0].replace(" ", "")
        for clave, cantidad in (("pose=", 6), ("joint=", 6)):
            if primero.lower().startswith(clave):
                try:
                    numeros = _numeros(primero[len(clave) :])
                except ValueError:
                    raise ErrorDeComando(-30001) from None
                if len(numeros) != cantidad:
                    raise ErrorDeComando(-20000)
                return clave[:-1], numeros
        raise ErrorDeComando(-30001)

    def _porcentajes(self, opciones: dict[str, float]) -> tuple[float, float]:
        velocidad, aceleracion = opciones.get("v", 100.0), opciones.get("a", 100.0)
        if not 1 <= velocidad <= 100:
            raise ErrorDeComando(-60001)
        if not 1 <= aceleracion <= 100:
            raise ErrorDeComando(-60001)
        return velocidad, aceleracion

    # --- comandos de control --------------------------------------------------------------------------------------------
    def _requestcontrol(self, p, s):
        self.simulador.control_tcp = True
        self.simulador.fallos.no_tcp = False
        return ""

    def _poweron(self, p, s):
        self.simulador.encendido = True
        return ""

    def _enablerobot(self, p, s):
        sim = self.simulador
        if sim.fallos.alarma or sim.fallos.colision:
            raise ErrorDeComando(-2)
        sim.encendido = sim.habilitado = True
        return ""

    def _disablerobot(self, p, s):
        self.simulador.habilitado = False
        self.simulador.detener()
        return ""

    def _clearerror(self, p, s):
        self.simulador.limpiar_errores()
        return ""

    def _stop(self, p, s):
        self.simulador.detener()
        self.simulador.pausa_robot = False
        return ""

    def _pause(self, p, s):
        self.simulador.pausa_robot = True
        return ""

    def _continue(self, p, s):
        self.simulador.pausa_robot = False
        return ""

    def _speedfactor(self, p, s):
        self._exigir(p, 1)
        try:
            valor = int(float(p[0]))
        except ValueError:
            raise ErrorDeComando(-30001) from None
        if not 1 <= valor <= 100:
            raise ErrorDeComando(-40001)
        self.simulador.velocidad_global = valor
        return ""

    def _ignorado(self, p, s):
        return ""

    def _startdrag(self, p, s):
        sim = self.simulador
        if sim.fallos.alarma:
            raise ErrorDeComando(-2)
        sim.arrastrando = True
        return ""

    def _stopdrag(self, p, s):
        self.simulador.arrastrando = False
        return ""

    # --- lectura ---------------------------------------------------------------------------------------------------------
    def _robotmode(self, p, s):
        return str(self.simulador.modo())

    def _getpose(self, p, s):
        return _formato(self.simulador.pose)

    def _getangle(self, p, s):
        return _formato(self.simulador.angulos)

    def _geterrorid(self, p, s):
        sim = self.simulador
        codigos = [1] if sim.fallos.alarma else [99] if sim.fallos.colision else []
        return "[" + ",".join(map(str, codigos)) + "]"

    def _getcurrentcommandid(self, p, s):
        sim = self.simulador
        return str(sim.actual.identificador if sim.actual else sim.siguiente_id - 1)

    def _positivekin(self, p, s):
        from brazo_base.simulador import cinematica

        self._exigir(p, 6, 8)
        return _formato(cinematica.pose_para_angulos(tuple(float(v) for v in p[:6])))

    # --- movimiento ------------------------------------------------------------------------------------------------------
    def _mov(self, articular: bool):
        def manejador(p, s):
            sim = self.simulador
            tipo, numeros = self._punto(p)
            opciones = self._opciones(p[1:])
            velocidad, aceleracion = self._porcentajes(opciones)
            velocidad_abs = opciones.get("speed") if not articular else None
            if tipo == "joint":
                identificador = sim.encolar_angulos(numeros, velocidad, aceleracion)
            else:
                identificador = sim.encolar_pose(numeros, articular, velocidad, aceleracion, velocidad_abs)
            return str(identificador)

        return manejador

    def _movj(self, p, s):
        return self._mov(True)(p, s)

    def _movl(self, p, s):
        return self._mov(False)(p, s)

    def _relmovluser(self, p, s):
        self._exigir(p, 6, 12)
        sim = self.simulador
        try:
            dx, dy, dz = (float(v) for v in p[:3])
        except ValueError:
            raise ErrorDeComando(-30001) from None
        opciones = self._opciones(p[6:])
        velocidad, aceleracion = self._porcentajes(opciones)
        pose = sim.pose_para_relativo(dx, dy, dz)
        return str(sim.encolar_pose(pose, False, velocidad, aceleracion, opciones.get("speed")))

    # --- Modbus hacia la pinza -----------------------------------------------------------------------------------------
    def _settool485(self, p, s):
        self._exigir(p, 3, 5)
        self.tool485_configurado = True
        return ""

    def _modbuscreate(self, p, s):
        self._exigir(p, 4)
        sim = self.simulador
        direccion, puerto = p[0].strip('"'), int(float(p[1]))
        if sim.fallos.pinza_no_responde or not self.tool485_configurado:
            raise ErrorDeComando(-1, "no hay respuesta del RS485 de la herramienta")
        if direccion != "127.0.0.1" or puerto != sim.parametros.robot.puerto_modbus_pinza:
            raise ErrorDeComando(-1, f"no hay ningún esclavo Modbus en {direccion}:{puerto}")
        if len(self.maestros) >= sim.parametros.robot.maestros_modbus_max:
            raise ErrorDeComando(-1, "ya hay 5 maestros Modbus abiertos")
        indice = self._siguiente_maestro
        while indice in self.maestros:
            indice += 1
        self.maestros[indice] = (int(float(p[2])),)
        self._siguiente_maestro = 0
        s.maestros.add(indice)
        return str(indice)

    def _modbusclose(self, p, s):
        self._exigir(p, 1)
        indice = int(float(p[0]))
        if indice not in self.maestros:
            raise ErrorDeComando(-1)
        del self.maestros[indice]
        s.maestros.discard(indice)
        return ""

    def _maestro_valido(self, p) -> int:
        sim = self.simulador
        indice = int(float(p[0]))
        if indice not in self.maestros:
            raise ErrorDeComando(-1, "maestro Modbus inexistente")
        if sim.fallos.pinza_no_responde:
            raise ErrorDeComando(-1, "la pinza no responde")
        return indice

    def _getholdregs(self, p, s):
        self._exigir(p, 3, 4)
        self._maestro_valido(p)
        direccion, cantidad = int(float(p[1])), int(float(p[2]))
        valores = []
        for desplazamiento in range(cantidad):
            valor = self.simulador.pinza.leer(direccion + desplazamiento)
            if valor is None:
                raise ErrorDeComando(-1, f"registro 0x{direccion + desplazamiento:04X} inexistente")
            valores.append(valor)
        return ",".join(map(str, valores))

    def _setholdregs(self, p, s):
        self._exigir(p, 4, 5)
        self._maestro_valido(p)
        direccion, cantidad = int(float(p[1])), int(float(p[2]))
        valores = _numeros(p[3])
        if len(valores) != cantidad:
            raise ErrorDeComando(-20000)
        for desplazamiento, valor in enumerate(valores):
            if not self.simulador.pinza.escribir(direccion + desplazamiento, int(valor)):
                raise ErrorDeComando(-1, f"registro 0x{direccion + desplazamiento:04X} inexistente")
        return ""

    COMANDOS = {
        "requestcontrol": _requestcontrol, "poweron": _poweron, "enablerobot": _enablerobot, "disablerobot": _disablerobot,
        "clearerror": _clearerror, "stop": _stop, "pause": _pause, "continue": _continue, "speedfactor": _speedfactor,
        "accj": _ignorado, "accl": _ignorado, "velj": _ignorado, "vell": _ignorado, "cp": _ignorado, "user": _ignorado, "tool": _ignorado,
        "setcollisionlevel": _ignorado, "startdrag": _startdrag, "stopdrag": _stopdrag,
        "robotmode": _robotmode, "getpose": _getpose, "getangle": _getangle, "geterrorid": _geterrorid,
        "getcurrentcommandid": _getcurrentcommandid, "positivekin": _positivekin,
        "movj": _movj, "movl": _movl, "relmovluser": _relmovluser,
        "settool485": _settool485, "modbuscreate": _modbuscreate, "modbusclose": _modbusclose,
        "getholdregs": _getholdregs, "setholdregs": _setholdregs,
    }
