"""`BrazoRemoto`: el `brazo` que ve un script pegado en la consola del panel.

El script corre en un proceso aparte, pero NO se conecta al brazo: le pide cada cosa al servidor por HTTP (la plataforma es la única dueña del brazo, así que las
validaciones, las zonas y el botón de parar siguen valiendo y el panel ve moverse el brazo en vivo). Tiene los mismos métodos que `Brazo`, así que un script que anda
en la consola anda igual con `with Brazo() as brazo:` fuera de ella.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from brazo_base.errores import ErrorBrazo, NoAgarro, RecorridoProhibido


class _HerramientaRemota:
    def __init__(self, brazo: "BrazoRemoto"):
        self._brazo = brazo

    def abrir(self) -> None:
        self._brazo._tarea("/herramienta", {"accion": "abrir"})

    def cerrar(self) -> bool | None:
        """`True` si sostiene algo, `False` si no."""
        return (self._brazo._tarea("/herramienta", {"accion": "cerrar"}) or {}).get("sostiene")

    def abrir_a(self, fraccion: float) -> None:
        self._brazo._tarea("/herramienta", {"accion": "abrir_a", "valor": fraccion})

    def estado(self) -> dict:
        return self._brazo.estado().get("herramienta", {})


class BrazoRemoto:
    def __init__(self, url: str | None = None, intervalo: float = 0.1):
        self.url = (url or os.environ.get("BRAZO_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.intervalo = intervalo
        self.herramienta = _HerramientaRemota(self)

    # --- HTTP ---------------------------------------------------------------------------------------------------------------
    def _pedir(self, metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
        datos = None if cuerpo is None else json.dumps(cuerpo).encode()
        peticion = urllib.request.Request(self.url + ruta, data=datos, method=metodo, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                return json.loads(respuesta.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                cuerpo_error = json.loads(error.read())
            except ValueError:
                cuerpo_error = {}
            mensaje = cuerpo_error.get("error") or str(cuerpo_error.get("detail") or error.reason)
            if cuerpo_error.get("problemas"):
                raise RecorridoProhibido(cuerpo_error["problemas"]) from None
            raise ErrorBrazo(mensaje) from None
        except OSError as error:
            raise ErrorBrazo(f"No se pudo hablar con el servidor en {self.url}: {error}") from None

    def _tarea(self, ruta: str, cuerpo: dict) -> dict | None:
        """Pide algo que tarda (responde 202), espera a que termine y devuelve su resultado. Si falla o se cancela, lanza el error."""
        numero = self._pedir("POST", ruta, cuerpo)["id"]
        while True:
            tarea = self._pedir("GET", "/estado").get("tarea", {})
            if tarea.get("id") == numero and tarea.get("estado") != "en_curso":
                break
            time.sleep(self.intervalo)
        if tarea["estado"] == "error":
            raise (NoAgarro if "no sostiene" in (tarea.get("error") or "") or "no sintió" in (tarea.get("error") or "") else ErrorBrazo)(tarea.get("error") or "falló")
        if tarea["estado"] == "cancelada":
            raise ErrorBrazo("Cancelado por el usuario")
        return tarea.get("resultado")

    # --- lectura --------------------------------------------------------------------------------------------------------------
    def estado(self) -> dict:
        return self._pedir("GET", "/estado")

    def pose(self) -> tuple[float, ...]:
        return tuple(self.estado()["pose"])

    def angulos(self) -> tuple[float, ...]:
        return tuple(self.estado()["angulos"])

    # --- movimiento -----------------------------------------------------------------------------------------------------------
    def mover_a(self, x=None, y=None, z=None, rz=None, lineal=None) -> None:
        self._tarea("/mover", {"x": x, "y": y, "z": z, "rz": rz, "lineal": lineal})

    def mover_relativo(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self._tarea("/mover", {"dx": dx, "dy": dy, "dz": dz})

    def mover_articulaciones(self, angulos) -> None:
        self._tarea("/mover", {"angulos": list(angulos)})

    def ir_a(self, nombre: str) -> None:
        self._tarea("/mover", {"punto": nombre})

    def agarrar(self, objeto: str) -> None:
        self._tarea("/agarrar", {"objeto": objeto})

    def soltar_en(self, lugar: str) -> None:
        self._tarea("/soltar", {"lugar": lugar})

    def llevar(self, objeto: str, lugar: str) -> None:
        self._tarea("/llevar", {"desde": objeto, "hasta": lugar})

    def llevar_desde(self, desde: str, hasta: str, perfil: str = "defecto", volver_a: str | None = "descanso") -> None:
        self._tarea("/llevar-desde", {"desde": desde, "hasta": hasta, "perfil": perfil, "volver_a": volver_a})

    def ejecutar_rutina(self, nombre: str, factor: float = 1.0, confirmar: bool = False) -> None:
        self._tarea(f"/rutinas/{urllib.request.quote(nombre)}/ejecutar", {"factor": factor, "confirmar": confirmar})

    def parar(self) -> None:
        self._pedir("POST", "/parar", {})
