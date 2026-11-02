"""Rutinas: listas de pasos con nombre, guardadas como `<directorio>/<nombre>.json`. El formato es el del ajedrez (se pueden copiar tal cual).

Tipos de paso: `articulaciones` (los 6 ángulos y la velocidad), `pinza` (apertura 0 a 1000 y, opcional, fuerza y velocidad), `esperar` (segundos) y `rutina` (llama
a otra, así se componen). Este módulo solo guarda y valida; quien ejecuta es `Brazo.ejecutar_rutina`.

Seguridad: cada pose se valida con `geometria` (límites de articulación, mesa, tablero y choques entre eslabones), igual que el camino recto entre dos poses seguidas;
un salto grande entre dos poses se rechaza (hay que poner una pose intermedia) y una rutina solo se acepta para el brazo real si ya corrió completa en el simulador con
exactamente esos pasos (`huella`).

«posición inicial» es una rutina incorporada: sale del punto `descanso` de la celda y no se guarda ni se edita.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from brazo_base.errores import ErrorBrazo
from brazo_base.seguridad import geometria

LIMITES_ARTICULACIONES = geometria.LIMITES_ARTICULACIONES
INCORPORADAS = ("posición inicial",)
SALTO_MAXIMO_GRADOS = 150
PROFUNDIDAD_MAXIMA = 5
MAXIMO_PASOS = 200
_NOMBRE = re.compile(r"^[\w][\w \-]{0,39}$")


class ErrorRutina(ErrorBrazo):
    """Error al guardar o leer una rutina; `codigo` es tipo HTTP (404 no existe, 409 estado incorrecto, 422 dato inválido)."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo, self.mensaje = codigo, mensaje


def directorio_de(celda) -> Path:
    """Dónde se guardan las rutinas de una celda: `rutinas/` junto a su archivo. La celda de práctica viene dentro del paquete, así que usa `~/.brazo-base/rutinas`."""
    if celda.ruta and "datos" not in Path(celda.ruta).parts:
        return Path(celda.ruta).parent / "rutinas"
    return Path.home() / ".brazo-base" / "rutinas"


def _numero(valor, minimo: float, maximo: float, que: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not minimo <= valor <= maximo:
        raise ErrorRutina(422, f"{que} debe estar entre {minimo} y {maximo}")
    return float(valor)


def desenrollar(planos: list[dict], actuales: list[float]) -> list[dict]:
    """Las poses de la rutina corridas por vueltas completas (múltiplos de 360°) para que la primera quede lo más cerca posible de `actuales`.

    Un ángulo y ese mismo más 360° son la misma pose física, pero `MovJ` interpola en ángulos: de -45° a 302° la base daría casi una vuelta entera en vez de 13°. Cada
    articulación se corre solo si todas las poses de la rutina siguen dentro de su rango.
    """
    poses = [p for p in planos if p["tipo"] == "articulaciones"]
    if not poses:
        return planos
    desfases = []
    for i, (actual, objetivo) in enumerate(zip(actuales, poses[0]["angulos"])):
        desfase = 360 * round((actual - objetivo) / 360)
        minimo, maximo = LIMITES_ARTICULACIONES[i]
        desfases.append(desfase if desfase and all(minimo <= p["angulos"][i] + desfase <= maximo for p in poses) else 0)
    if not any(desfases):
        return planos
    return [{**p, "angulos": [a + d for a, d in zip(p["angulos"], desfases)]} if p["tipo"] == "articulaciones" else p for p in planos]


def describir_paso(paso: dict) -> str:
    if paso["tipo"] == "articulaciones":
        return "Ir a " + ", ".join(f"{a:g}" for a in paso["angulos"])
    if paso["tipo"] == "pinza":
        return f"Pinza a {paso['apertura']}"
    return f"Esperar {paso['segundos']:g} s"


def huella(planos: list[dict]) -> str:
    """Identifica exactamente qué hace una rutina (sus pasos ya aplanados): si cambia algo, cambia la huella y deja de estar validada."""
    return hashlib.sha256(json.dumps(planos, sort_keys=True).encode()).hexdigest()[:16]


class Rutinas:
    """Las rutinas de una celda. `z_tope_mm` es la altura de la superficie en el sistema de la brida (None si no se midió) y `largo_herramienta_m` el largo de la herramienta."""

    def __init__(self, directorio: Path, angulos_inicio: list[float] | None = None, z_tope_mm: float | None = None, largo_herramienta_m: float | None = None):
        self.directorio = Path(directorio)
        self.angulos_inicio, self.z_tope_mm = angulos_inicio, z_tope_mm
        self.largo_m = largo_herramienta_m or geometria.LARGO_PINZA_DEFECTO

    @classmethod
    def de_celda(cls, celda, directorio: Path | None = None) -> "Rutinas":
        inicio = celda.puntos.get("descanso", {}).get("angulos")
        z = celda.agarre.get("z_referencia_mm") if celda.modo_pose == "brida" else None
        return cls(directorio or directorio_de(celda), inicio, z, celda.largo_herramienta_mm / 1000 if celda.largo_herramienta_mm else None)

    # --- archivos ---------------------------------------------------------------------------------------------------------
    def _ruta(self, nombre) -> Path:
        if not isinstance(nombre, str) or not _NOMBRE.match(nombre):
            raise ErrorRutina(422, "El nombre debe tener de 1 a 40 letras, números, espacios, guiones o guiones bajos")
        return self.directorio / f"{nombre}.json"

    def _incorporada(self, nombre: str) -> dict | None:
        if nombre == "posición inicial" and self.angulos_inicio:
            return {"pasos": [{"tipo": "articulaciones", "angulos": list(self.angulos_inicio), "velocidad": 20}], "actualizada": None}
        return None

    def _leer(self, nombre: str) -> dict:
        if (incorporada := self._incorporada(nombre)) is not None:
            return incorporada
        ruta = self._ruta(nombre)
        if not ruta.exists():
            raise ErrorRutina(404, f"No existe la rutina «{nombre}»")
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ErrorRutina(422, f"La rutina «{nombre}» está dañada ({error}): borrala o arreglá {ruta}") from error

    # --- validación -------------------------------------------------------------------------------------------------------
    def validar_paso(self, paso: dict, indice: int) -> dict:
        """Paso limpio (solo los campos que corresponden) o `ErrorRutina` si algo está fuera de rango."""
        donde = f"Paso {indice}"
        if not isinstance(paso, dict):
            raise ErrorRutina(422, f"{donde}: formato inválido")
        tipo = paso.get("tipo")
        if tipo == "articulaciones":
            angulos = paso.get("angulos")
            if not isinstance(angulos, list) or len(angulos) != 6:
                raise ErrorRutina(422, f"{donde}: hacen falta los 6 ángulos J1 a J6")
            limpio = {"tipo": tipo, "angulos": [_numero(a, *limite, f"{donde}: J{i}") for i, (a, limite) in enumerate(zip(angulos, LIMITES_ARTICULACIONES), start=1)]}
            limpio["velocidad"] = int(_numero(paso.get("velocidad", 20), 1, 100, f"{donde}: la velocidad"))
            if problemas := geometria.problemas_de_pose(limpio["angulos"], self.z_tope_mm, self.largo_m):
                raise ErrorRutina(422, f"{donde}: pose imposible: {'; '.join(problemas[:2])}")
            return limpio
        if tipo == "pinza":
            limpio = {"tipo": tipo, "apertura": int(_numero(paso.get("apertura"), 0, 1000, f"{donde}: la apertura"))}
            for campo, minimo, maximo in (("fuerza", 20, 100), ("velocidad", 1, 100)):
                if paso.get(campo) is not None:
                    limpio[campo] = int(_numero(paso[campo], minimo, maximo, f"{donde}: {campo}"))
            return limpio
        if tipo == "esperar":
            return {"tipo": tipo, "segundos": _numero(paso.get("segundos"), 0, 30, f"{donde}: la espera")}
        if tipo == "rutina":
            self._ruta(paso.get("nombre"))
            return {"tipo": tipo, "nombre": paso["nombre"]}
        raise ErrorRutina(422, f"{donde}: tipo desconocido (articulaciones, pinza, esperar o rutina)")

    def aplanar(self, pasos: list[dict], _profundidad: int = 0, _en_curso: tuple[str, ...] = ()) -> list[dict]:
        """Los pasos con cada `rutina` reemplazada por los suyos, recursivamente. Falla si llama a una que no existe, si hay un ciclo o si la anidación pasa del máximo."""
        if _profundidad > PROFUNDIDAD_MAXIMA:
            raise ErrorRutina(422, f"Demasiadas rutinas anidadas (máximo {PROFUNDIDAD_MAXIMA})")
        planos: list[dict] = []
        for paso in pasos:
            if paso["tipo"] != "rutina":
                planos.append(paso)
                continue
            if paso["nombre"] in _en_curso:
                raise ErrorRutina(422, f"La rutina «{paso['nombre']}» se llama a sí misma ({' → '.join((*_en_curso, paso['nombre']))})")
            planos.extend(self.aplanar(self._leer(paso["nombre"])["pasos"], _profundidad + 1, (*_en_curso, paso["nombre"])))
        return planos

    @staticmethod
    def revisar_saltos(planos: list[dict]) -> None:
        """Rechaza dos poses seguidas que difieran en alguna articulación más de `SALTO_MAXIMO_GRADOS`."""
        anterior = None
        for paso in planos:
            if paso["tipo"] != "articulaciones":
                continue
            if anterior is not None:
                for j, (a, b) in enumerate(zip(anterior, paso["angulos"]), start=1):
                    if abs(a - b) > SALTO_MAXIMO_GRADOS:
                        raise ErrorRutina(422, f"J{j} salta {abs(a - b):.0f}° entre dos poses seguidas (máximo {SALTO_MAXIMO_GRADOS}°): agregá una pose intermedia")
            anterior = paso["angulos"]

    def revisar_trayectorias(self, planos: list[dict]) -> None:
        """Rechaza dos poses seguidas cuyo camino recto en articulaciones (el de `MovJ`) pase por una pose imposible (mesa, tablero o choque)."""
        anterior, numero_anterior = None, 0
        for numero, paso in enumerate(planos, start=1):
            if paso["tipo"] != "articulaciones":
                continue
            if anterior is not None and (problemas := geometria.problemas_de_trayectoria(anterior, paso["angulos"], self.z_tope_mm, self.largo_m)):
                raise ErrorRutina(422, f"Entre el paso {numero_anterior} y el {numero} el brazo pasaría por una pose imposible: {problemas[0]}. Agregá una pose intermedia que lo rodee")
            anterior, numero_anterior = paso["angulos"], numero

    # --- API ----------------------------------------------------------------------------------------------------------------
    def obtener(self, nombre: str) -> dict:
        """`{"nombre", "pasos", "validada", "actualizada", "incorporada"}`; `validada` es `True` si corrió completa en el simulador con estos mismos pasos."""
        datos = self._leer(nombre)
        incorporada = nombre in INCORPORADAS
        try:
            al_dia = incorporada or datos.get("huella_validada") == huella(self.aplanar(datos["pasos"], _en_curso=(nombre,)))
        except ErrorRutina:
            al_dia = False  # llama a una rutina que ya no existe
        return {"nombre": nombre, "pasos": datos["pasos"], "validada": al_dia, "actualizada": datos.get("actualizada"), "incorporada": incorporada}

    def listar(self) -> list[dict]:
        resumen = [{"nombre": n, "pasos": len(r["pasos"]), "validada": True, "actualizada": None, "incorporada": True} for n in INCORPORADAS if (r := self._incorporada(n)) is not None]
        if not self.directorio.exists():
            return resumen
        for archivo in sorted(self.directorio.glob("*.json")):
            try:
                r = self.obtener(archivo.stem)
            except ErrorRutina:
                continue
            resumen.append({"nombre": r["nombre"], "pasos": len(r["pasos"]), "validada": r["validada"], "actualizada": r["actualizada"], "incorporada": False})
        return resumen

    def guardar(self, nombre: str, pasos: list[dict]) -> dict:
        """Valida y guarda `pasos` como la rutina `nombre` (la reemplaza si existe; deja de estar validada para el brazo real)."""
        ruta = self._ruta(nombre)
        if nombre in INCORPORADAS:
            raise ErrorRutina(409, f"«{nombre}» es una rutina incorporada y no se puede cambiar: guardá una copia con otro nombre")
        if not isinstance(pasos, list) or not pasos:
            raise ErrorRutina(422, "La rutina necesita al menos un paso")
        if len(pasos) > MAXIMO_PASOS:
            raise ErrorRutina(422, f"Máximo {MAXIMO_PASOS} pasos por rutina")
        limpios = [self.validar_paso(p, i) for i, p in enumerate(pasos, start=1)]
        planos = self.aplanar(limpios, _en_curso=(nombre,))
        self.revisar_saltos(planos)
        self.revisar_trayectorias(planos)
        self.directorio.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"pasos": limpios, "actualizada": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=1), encoding="utf-8")
        return self.obtener(nombre)

    def borrar(self, nombre: str) -> None:
        ruta = self._ruta(nombre)
        if nombre in INCORPORADAS:
            raise ErrorRutina(409, f"«{nombre}» es una rutina incorporada y no se puede borrar")
        if not ruta.exists():
            raise ErrorRutina(404, f"No existe la rutina «{nombre}»")
        ruta.unlink()

    def pasos_para_ejecutar(self, nombre: str) -> tuple[list[dict], str]:
        """`(pasos aplanados, huella)` listos para correr: ya revisados (rangos, ciclos y saltos entre poses)."""
        planos = self.aplanar(self._leer(nombre)["pasos"], _en_curso=(nombre,))
        self.revisar_saltos(planos)
        self.revisar_trayectorias(planos)
        return planos, huella(planos)

    def marcar_validada(self, nombre: str, huella_ejecutada: str) -> None:
        """Anota que la rutina corrió completa en el simulador con esa huella (así el brazo real la acepta mientras no cambie)."""
        if nombre in INCORPORADAS:
            return
        datos = self._leer(nombre)
        datos["huella_validada"] = huella_ejecutada
        self._ruta(nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
