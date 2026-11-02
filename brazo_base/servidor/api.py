"""API HTTP de la plataforma: lo mismo que la clase `Brazo`, para usarlo desde cualquier lenguaje. Escucha solo en 127.0.0.1 por defecto.

Errores: `{"error": "mensaje que dice qué hacer"}` con 409 (estado incorrecto), 422 (dato inválido o recorrido prohibido), 503 (el brazo o la herramienta no responde).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from brazo_base import ErrorBrazo, ErrorDelControlador, HerramientaNoResponde, NoAgarro, NoHabilitado, RecorridoProhibido, SinConexion
from brazo_base.celda.archivos import cargar_herramienta, celda_desde_dict, guardar_celda
from brazo_base.servidor.servicio import Conflicto, ServicioBrazo, servicio as servicio_global

PANEL = Path(__file__).parent / "panel"
ORIGENES_LOCALES = r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|null)$"
"""Solo páginas del propio equipo (y archivos abiertos con file://) pueden llamar a la API desde un navegador."""
MAXIMO_VELOCIDAD_SIMULACION = 50.0


class ConectarPedido(BaseModel):
    destino: str = "simulador"
    celda: str | None = None
    velocidad: int | None = Field(None, ge=1, le=100)
    velocidad_simulacion: float = Field(1.0, gt=0, le=MAXIMO_VELOCIDAD_SIMULACION)
    confirmar_real: bool = False


class MoverPedido(BaseModel):
    x: float | None = None
    y: float | None = None
    z: float | None = None
    rz: float | None = None
    lineal: bool = True
    punto: str | None = None
    angulos: list[float] | None = Field(None, min_length=6, max_length=6)


class HerramientaPedido(BaseModel):
    accion: str
    valor: float | None = None


class LlevarPedido(BaseModel):
    desde: str
    hasta: str


class EnsayoPedido(BaseModel):
    tipo: str
    x: float | None = None
    y: float | None = None
    z: float | None = None
    desde: str | None = None
    hasta: str | None = None
    angulos: list[float] | None = Field(None, min_length=6, max_length=6)


class CeldaPedido(BaseModel):
    ruta: str
    celda: dict


class PuntoPedido(BaseModel):
    guardar: bool = False


class FalloPedido(BaseModel):
    fallo: str
    activo: bool = True


def crear_app(servicio: ServicioBrazo | None = None) -> FastAPI:
    svc = servicio or servicio_global
    app = FastAPI(title="brazo-base", version="0.1.0", description="Controla el Dobot CR5AS (simulador o real) por HTTP")
    app.add_middleware(CORSMiddleware, allow_origin_regex=ORIGENES_LOCALES, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ErrorBrazo)
    async def _error_brazo(_: Request, error: ErrorBrazo):
        codigo = 409 if isinstance(error, (Conflicto, SinConexion, NoHabilitado, NoAgarro)) else 503 if isinstance(error, (HerramientaNoResponde, ErrorDelControlador)) else 422
        return JSONResponse({"error": str(error), **({"problemas": error.problemas} if isinstance(error, RecorridoProhibido) else {})}, status_code=codigo)

    @app.exception_handler(ValueError)
    async def _error_valor(_: Request, error: ValueError):
        return JSONResponse({"error": str(error)}, status_code=422)

    # --- conexión y seguridad --------------------------------------------------------------------------------------------------
    @app.post("/conectar")
    def conectar(p: ConectarPedido):
        if p.destino == "real" and not p.confirmar_real:
            raise Conflicto("Para conectar con el brazo REAL mandá «confirmar_real»: true. El simulador no necesita confirmación.")
        svc.conectar(p.destino, p.celda, p.velocidad, p.velocidad_simulacion)
        return svc.estado()

    @app.post("/desconectar")
    def desconectar():
        svc.desconectar()
        return {"conectado": False}

    @app.post("/habilitar")
    def habilitar():
        svc.exigir_brazo().habilitar()
        return svc.estado()

    @app.post("/parar")
    def parar():
        svc.parar()
        return {"ok": True}

    @app.post("/limpiar-error")
    def limpiar_error():
        svc.exigir_brazo().limpiar_error()
        return {"ok": True}

    # --- lectura -----------------------------------------------------------------------------------------------------------------
    @app.get("/estado")
    def estado():
        return svc.estado()

    @app.websocket("/telemetria")
    async def telemetria(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(await asyncio.to_thread(svc.estado))
                await asyncio.sleep(0.2)
        except (WebSocketDisconnect, RuntimeError):
            pass

    # --- movimiento (validado antes; responde 202 y la tarea se sigue en /estado) ---------------------------------------------------
    @app.post("/mover", status_code=202)
    def mover(p: MoverPedido):
        brazo = svc.exigir_brazo()
        if p.angulos is not None:
            _exigir_ok(brazo.ensayo("articulaciones", angulos=p.angulos))
            return svc.lanzar("mover_articulaciones", lambda b: b.mover_articulaciones(p.angulos))
        if p.punto is not None:
            return svc.lanzar(f"ir_a {p.punto}", lambda b: b.ir_a(p.punto))
        if p.x is None and p.y is None and p.z is None:
            raise ValueError("Mandá x, y, z (mm), un «punto» con nombre o «angulos»")
        _exigir_ok(brazo.ensayo("mover", x=p.x, y=p.y, z=p.z))
        return svc.lanzar("mover_a", lambda b: b.mover_a(p.x, p.y, p.z, p.rz, p.lineal))

    @app.post("/herramienta", status_code=202)
    def herramienta(p: HerramientaPedido):
        svc.exigir_brazo()
        if p.accion == "abrir":
            return svc.lanzar("herramienta.abrir", lambda b: b._herramienta().abrir())
        if p.accion == "cerrar":
            return svc.lanzar("herramienta.cerrar", lambda b: {"sostiene": b._herramienta().cerrar()})
        if p.accion == "abrir_a":
            if p.valor is None or not 0 <= p.valor <= 1:
                raise ValueError("abrir_a necesita «valor» entre 0 (cerrada) y 1 (abierta)")
            return svc.lanzar("herramienta.abrir_a", lambda b: b._herramienta().abrir_a(p.valor))
        raise ValueError("accion tiene que ser abrir, cerrar o abrir_a")

    @app.post("/llevar", status_code=202)
    def llevar(p: LlevarPedido):
        _exigir_ok(svc.exigir_brazo().ensayo("llevar", objeto=p.desde, lugar=p.hasta))
        return svc.lanzar(f"llevar {p.desde} -> {p.hasta}", lambda b: b.llevar(p.desde, p.hasta))

    @app.post("/ensayo")
    def ensayo(p: EnsayoPedido):
        brazo = svc.exigir_brazo()
        if p.tipo == "llevar":
            return brazo.ensayo("llevar", objeto=p.desde, lugar=p.hasta)
        if p.tipo == "articulaciones":
            return brazo.ensayo("articulaciones", angulos=p.angulos)
        return brazo.ensayo(p.tipo, x=p.x, y=p.y, z=p.z)

    # --- celda y puntos ------------------------------------------------------------------------------------------------------------
    @app.get("/celda")
    def leer_celda():
        return svc.celda()

    @app.put("/celda")
    def cambiar_celda(p: CeldaPedido):
        """Valida la celda y la guarda en `ruta` (atómico, con `.bak`). Solo sin conexión: mientras hay una se está usando."""
        if svc.brazo is not None:
            raise Conflicto("Desconectá antes de cambiar la celda (se usa mientras hay conexión)")
        ruta = Path(p.ruta)
        if ruta.suffix != ".json":
            raise ValueError("La ruta tiene que ser un archivo .json")
        celda = celda_desde_dict(p.celda, str(ruta))
        cargar_herramienta(celda, ruta.parent)
        guardar_celda(celda, ruta)
        return {"ok": True, "ruta": str(ruta), "avisos": celda.avisos}

    @app.put("/puntos/{nombre}")
    def guardar_punto(nombre: str, p: PuntoPedido):
        """Guarda los ángulos actuales como punto con nombre (en la celda en memoria; en disco solo con `guardar` y celda que no sea la demo)."""
        brazo = svc.exigir_brazo()
        if not nombre.isidentifier():
            raise ValueError("El nombre del punto tiene que ser una palabra sin espacios (letras, números y _)")
        brazo.celda.puntos[nombre] = {"angulos": [round(a, 4) for a in brazo.angulos()]}
        if p.guardar:
            if not brazo.celda.ruta or "datos" in Path(brazo.celda.ruta).parts:
                raise Conflicto("Esta celda no tiene archivo propio (es la de práctica): el punto queda solo en memoria")
            guardar_celda(brazo.celda)
        return {"punto": nombre, **brazo.celda.puntos[nombre]}

    @app.post("/simulador/fallo")
    def fallo(p: FalloPedido):
        brazo = svc.exigir_brazo()
        if brazo.simulador is None:
            raise Conflicto("Los fallos provocados solo existen en el simulador")
        brazo.simulador.provocar(p.fallo, p.activo)
        return {"ok": True}

    # --- panel ------------------------------------------------------------------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    def raiz():
        return FileResponse(PANEL / "index.html")

    app.mount("/panel", StaticFiles(directory=PANEL), name="panel")
    return app


def _exigir_ok(resultado: dict) -> None:
    if not resultado["ok"]:
        raise RecorridoProhibido(resultado["problemas"])


app = crear_app()
