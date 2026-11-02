"""Corre un script de usuario en un proceso aparte, con tiempo límite y salida en vivo.

El script ve una variable `brazo` (un `BrazoRemoto`: le pide todo al servidor, que sigue siendo el único dueño del brazo). Es un programa de Python con los permisos del
usuario que lo pegó: la consola es una herramienta de laboratorio que corre en tu propio equipo (el servidor solo escucha en 127.0.0.1 y rechaza pedidos de páginas ajenas).

Regla del brazo real: un script solo se acepta si ya terminó SIN errores en el simulador con exactamente ese código (misma huella, como las rutinas) y con confirmación.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

LIMITE_POR_DEFECTO_S = 120.0
LIMITE_MAXIMO_S = 600.0
MAXIMO_LINEAS = 2000
MAXIMO_CARACTERES_LINEA = 500
MAXIMO_CODIGO = 20000

ARRANQUE = """
import os, sys
from brazo_base.scripts.remoto import BrazoRemoto
codigo = open(sys.argv[1], encoding="utf-8").read()
brazo = BrazoRemoto(os.environ["BRAZO_URL"])
exec(compile(codigo, "script", "exec"), {"brazo": brazo, "BrazoRemoto": BrazoRemoto, "__name__": "__main__"})
"""


def huella_de(codigo: str) -> str:
    """Identifica el código ignorando fines de línea y espacios al final: si cambia algo más, cambia la huella y deja de estar validado."""
    normal = "\n".join(linea.rstrip() for linea in codigo.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n"))
    return hashlib.sha256(normal.encode()).hexdigest()[:16]


class Validados:
    """Las huellas de los scripts que terminaron sin errores en el simulador (un archivo JSON; la clave es la huella)."""

    def __init__(self, archivo: Path):
        self.archivo = Path(archivo)

    def _leer(self) -> dict:
        try:
            return json.loads(self.archivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def esta(self, huella: str) -> bool:
        return huella in self._leer()

    def marcar(self, huella: str) -> None:
        datos = self._leer()
        datos[huella] = {"fecha": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        self.archivo.write_text(json.dumps(datos, indent=1), encoding="utf-8")


class ErrorScript(Exception):
    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo, self.mensaje = codigo, mensaje


class EjecutorScripts:
    def __init__(self, validados: Validados):
        self.validados = validados
        self._cerrojo = threading.RLock()
        self._proceso: subprocess.Popen | None = None
        self._carpeta: str | None = None
        self._lineas: list[str] = []
        self._truncado = False
        self.estado = "libre"  # libre | corriendo | terminado | error | cancelado | tiempo
        self.codigo_salida: int | None = None
        self.huella: str | None = None
        self.inicio = 0.0
        self.fin = 0.0

    # --- control ----------------------------------------------------------------------------------------------------------
    def corriendo(self) -> bool:
        return self.estado == "corriendo"

    def iniciar(self, codigo: str, url: str, destino: str, confirmar: bool = False, limite_s: float = LIMITE_POR_DEFECTO_S) -> str:
        """Arranca el script y devuelve su huella. Lanza `ErrorScript` (409 estado incorrecto, 422 dato inválido) si no se puede."""
        if not isinstance(codigo, str) or not codigo.strip():
            raise ErrorScript(422, "Pegá un script: el código está vacío")
        if len(codigo) > MAXIMO_CODIGO:
            raise ErrorScript(422, f"El script es demasiado largo (máximo {MAXIMO_CODIGO} caracteres)")
        if not 1 <= limite_s <= LIMITE_MAXIMO_S:
            raise ErrorScript(422, f"El tiempo límite va de 1 a {LIMITE_MAXIMO_S:g} segundos")
        try:
            compile(codigo, "script", "exec")
        except SyntaxError as error:
            raise ErrorScript(422, f"El script tiene un error de sintaxis en la línea {error.lineno}: {error.msg}") from None
        huella = huella_de(codigo)
        if destino == "real":
            if not self.validados.esta(huella):
                raise ErrorScript(409, "Este script todavía no terminó sin errores en el simulador con exactamente este código. Corrélo antes con el simulador conectado; si cambiás algo, hay que repetirlo.")
            if not confirmar:
                raise ErrorScript(409, "Confirmá que querés correr el script en el brazo real (confirmar=true)")
        with self._cerrojo:
            if self.corriendo():
                raise ErrorScript(409, "Ya hay un script corriendo: esperá a que termine o pará")
            self._limpiar_carpeta()
            self._carpeta = tempfile.mkdtemp(prefix="brazo_script_")
            archivo = Path(self._carpeta) / "script.py"
            archivo.write_text(codigo, encoding="utf-8")
            entorno = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR")}
            entorno["BRAZO_URL"] = url
            self._proceso = subprocess.Popen([sys.executable, "-I", "-u", "-c", ARRANQUE, str(archivo)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                             text=True, encoding="utf-8", errors="replace", cwd=self._carpeta, env=entorno, start_new_session=True)
            self._lineas, self._truncado, self.estado, self.codigo_salida, self.huella = [], False, "corriendo", None, huella
            self.inicio, self.fin = time.monotonic(), 0.0
            proceso = self._proceso
        threading.Thread(target=self._leer_salida, args=(proceso,), daemon=True).start()
        threading.Thread(target=self._vigilar, args=(proceso, limite_s, destino), daemon=True).start()
        return huella

    def parar(self) -> None:
        with self._cerrojo:
            if self.corriendo():
                self.estado = "cancelado"
                self._matar(self._proceso)

    @staticmethod
    def _matar(proceso: subprocess.Popen | None) -> None:
        if proceso is None or proceso.poll() is not None:
            return
        try:
            os.killpg(proceso.pid, 15)
            try:
                proceso.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proceso.pid, 9)
        except (ProcessLookupError, PermissionError):
            pass

    # --- hilos --------------------------------------------------------------------------------------------------------------
    def _leer_salida(self, proceso: subprocess.Popen) -> None:
        for linea in proceso.stdout:
            with self._cerrojo:
                if proceso is not self._proceso:
                    return
                if len(self._lineas) >= MAXIMO_LINEAS:
                    if not self._truncado:
                        self._lineas.append(f"[…salida cortada: más de {MAXIMO_LINEAS} líneas…]")
                        self._truncado = True
                    continue
                self._lineas.append(linea.rstrip("\n")[:MAXIMO_CARACTERES_LINEA])

    def _vigilar(self, proceso: subprocess.Popen, limite_s: float, destino: str) -> None:
        try:
            proceso.wait(timeout=limite_s)
            tiempo = False
        except subprocess.TimeoutExpired:
            tiempo = True
            self._matar(proceso)
        time.sleep(0.05)  # deja que el lector termine de vaciar la salida
        with self._cerrojo:
            if proceso is not self._proceso:
                return
            self.codigo_salida, self.fin = proceso.returncode, time.monotonic()
            if self.estado == "cancelado":
                pass
            elif tiempo:
                self.estado = "tiempo"
                self._lineas.append(f"[el script pasó el tiempo límite ({limite_s:g} s) y se cortó]")
            elif proceso.returncode == 0:
                self.estado = "terminado"
                if destino == "simulador" and self.huella:
                    self.validados.marcar(self.huella)
            else:
                self.estado = "error"

    def _limpiar_carpeta(self) -> None:
        if self._carpeta:
            shutil.rmtree(self._carpeta, ignore_errors=True)
            self._carpeta = None

    # --- lectura --------------------------------------------------------------------------------------------------------------
    def leer(self, desde: int = 0) -> dict:
        with self._cerrojo:
            fin = self.fin or time.monotonic()
            return {"estado": self.estado, "salida": self._lineas[desde:], "total": len(self._lineas), "codigo_salida": self.codigo_salida, "huella": self.huella,
                    "duracion_s": round(fin - self.inicio, 1) if self.inicio else 0.0,
                    "validado_para_real": bool(self.huella and self.validados.esta(self.huella))}
