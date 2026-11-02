"""API HTTP de la plataforma: lo mismo que la clase `Brazo`, para usarlo desde cualquier lenguaje. Escucha solo en 127.0.0.1 por defecto.

Errores: `{"error": "mensaje que dice qué hacer"}` con 409 (estado incorrecto), 422 (dato inválido o recorrido prohibido), 503 (el brazo o la herramienta no responde).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import re

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from brazo_base import ErrorBrazo, ErrorDelControlador, HerramientaNoResponde, NoAgarro, NoHabilitado, RecorridoProhibido, SinConexion
from brazo_base.calibracion import herramienta as calib_herramienta
from brazo_base.calibracion.superficie import calibrar_superficie
from brazo_base.celda.archivos import cargar_herramienta, celda_desde_dict, guardar_celda
from brazo_base.rutinas import ErrorRutina
from brazo_base.scripts.ejecutor import ErrorScript, LIMITE_POR_DEFECTO_S, huella_de
from brazo_base.servidor.servicio import Conflicto, ServicioBrazo, servicio as servicio_global

PANEL = Path(__file__).parent / "panel"
ORIGENES_LOCALES = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
"""Solo páginas servidas desde este equipo pueden llamar a la API desde un navegador (ni siquiera `null`, el origen de un archivo abierto con file:// o de un iframe aislado)."""
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
    dx: float | None = None
    dy: float | None = None
    dz: float | None = None
    lineal: bool | None = None
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


class AgarrarPedido(BaseModel):
    objeto: str


class SoltarPedido(BaseModel):
    lugar: str


class LlevarDesdePedido(BaseModel):
    desde: str
    hasta: str
    perfil: str = "defecto"
    volver_a: str | None = "descanso"


class RutinaPedido(BaseModel):
    pasos: list[dict] = Field(min_length=1, max_length=200)


class EjecutarRutinaPedido(BaseModel):
    factor: float = Field(1.0, ge=0.25, le=2.0)
    confirmar: bool = False


class ScriptPedido(BaseModel):
    codigo: str = Field(max_length=20000)
    confirmar: bool = False
    limite_segundos: float = Field(LIMITE_POR_DEFECTO_S, ge=1, le=600)


class HuellaPedido(BaseModel):
    codigo: str = Field(max_length=20000)


class SuperficiePedido(BaseModel):
    nombre: str = Field(pattern=r"^\w{1,40}$")
    puntos: dict[str, list[float]]
    filas: int = Field(ge=2, le=64)
    columnas: int = Field(ge=2, le=26)
    z_mm: float | None = None
    corrimiento_mm: list[float] = Field([0.0, 0.0], min_length=2, max_length=2)
    borde_mm: float = Field(0.0, ge=0)
    guardar: bool = False


class LargoPedido(BaseModel):
    z_brida_mm: float | None = None
    z_superficie_mm: float | None = None
    poses: list[list[float]] | None = None


class LugarPedido(BaseModel):
    z: float | None = None
    guardar: bool = False


class PuntoPedido(BaseModel):
    guardar: bool = False


class FalloPedido(BaseModel):
    fallo: str
    activo: bool = True


def crear_app(servicio: ServicioBrazo | None = None) -> FastAPI:
    svc = servicio or servicio_global
    app = FastAPI(title="brazo-base", version="0.1.0", description="Controla el Dobot CR5AS (simulador o real) por HTTP")
    app.add_middleware(CORSMiddleware, allow_origin_regex=ORIGENES_LOCALES, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def _sin_cache_en_el_panel(request: Request, call_next):
        respuesta = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/panel/"):
            respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta

    @app.middleware("http")
    async def _rechazar_paginas_ajenas(request: Request, call_next):
        """Un pedido que cambia algo y viene de una página de otro origen se rechaza (los navegadores mandan siempre `Origin` en pedidos entre sitios, aunque no haya preflight)."""
        origen = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origen is not None and not re.match(ORIGENES_LOCALES, origen):
            return JSONResponse({"error": f"Pedido rechazado: el origen {origen} no es de este equipo. La API solo acepta páginas de localhost."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ErrorScript)
    async def _error_script(_: Request, error: ErrorScript):
        return JSONResponse({"error": error.mensaje}, status_code=error.codigo)

    @app.exception_handler(ErrorRutina)
    async def _error_rutina(_: Request, error: ErrorRutina):
        return JSONResponse({"error": error.mensaje}, status_code=error.codigo)

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
                await asyncio.sleep(0.1)
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
        if any(v is not None for v in (p.dx, p.dy, p.dz)):  # relativo: la herramienta conserva su orientación
            dx, dy, dz = p.dx or 0.0, p.dy or 0.0, p.dz or 0.0
            ax, ay, az, *_ = brazo.pose()
            _exigir_ok(brazo.ensayo("mover", x=ax + dx, y=ay + dy, z=az + dz))
            return svc.lanzar("mover_relativo", lambda b: b.mover_relativo(dx, dy, dz))
        if p.x is None and p.y is None and p.z is None:
            raise ValueError("Mandá x, y, z (mm), dx, dy, dz (relativo), un «punto» con nombre o «angulos»")
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

    # --- más pick and place --------------------------------------------------------------------------------------------------------
    @app.post("/agarrar", status_code=202)
    def agarrar(p: AgarrarPedido):
        svc.exigir_brazo()
        return svc.lanzar(f"agarrar {p.objeto}", lambda b: b.agarrar(p.objeto))

    @app.post("/soltar", status_code=202)
    def soltar(p: SoltarPedido):
        svc.exigir_brazo()
        return svc.lanzar(f"soltar en {p.lugar}", lambda b: b.soltar_en(p.lugar))

    @app.post("/llevar-desde", status_code=202)
    def llevar_desde(p: LlevarDesdePedido):
        svc.exigir_brazo()
        return svc.lanzar(f"llevar {p.desde} -> {p.hasta}", lambda b: b.llevar_desde(p.desde, p.hasta, p.perfil, p.volver_a))

    # --- rutinas -----------------------------------------------------------------------------------------------------------------------
    @app.get("/rutinas")
    def listar_rutinas():
        return svc.exigir_brazo().rutinas.listar()

    @app.get("/rutinas/{nombre}")
    def leer_rutina(nombre: str):
        return svc.exigir_brazo().rutinas.obtener(nombre)

    @app.put("/rutinas/{nombre}")
    def guardar_rutina(nombre: str, p: RutinaPedido):
        return svc.exigir_brazo().rutinas.guardar(nombre, p.pasos)

    @app.delete("/rutinas/{nombre}")
    def borrar_rutina(nombre: str):
        svc.exigir_brazo().rutinas.borrar(nombre)
        return {"ok": True}

    @app.post("/rutinas/{nombre}/ejecutar", status_code=202)
    def ejecutar_rutina(nombre: str, p: EjecutarRutinaPedido):
        brazo = svc.exigir_brazo()
        brazo.comprobar_rutina(nombre, p.factor, p.confirmar)  # todo lo que se puede comprobar antes de mover, con respuesta directa

        def correr(b):
            def avance(i, n, texto):
                svc.tarea["mensaje"] = f"Paso {i}/{n}: {texto}"
            b.ejecutar_rutina(nombre, p.factor, p.confirmar, avance)

        return svc.lanzar(f"rutina «{nombre}»", correr)

    # --- consola de scripts --------------------------------------------------------------------------------------------------------------
    @app.post("/scripts/ejecutar", status_code=202)
    def ejecutar_script(p: ScriptPedido, request: Request):
        svc.exigir_brazo()
        if not svc.brazo._habilitado:
            raise Conflicto("El brazo no está habilitado: habilitalo antes de correr un script")
        huella = svc.scripts.iniciar(p.codigo, str(request.base_url).rstrip("/"), svc.destino or "simulador", p.confirmar, p.limite_segundos)
        return {"huella": huella, **svc.scripts.leer()}

    @app.get("/scripts/estado")
    def estado_script(desde: int = 0):
        return svc.scripts.leer(max(0, desde))

    @app.post("/scripts/parar")
    def parar_script():
        svc.scripts.parar()
        if svc.brazo is not None:
            svc.brazo.parar()
        return {"ok": True}

    @app.post("/scripts/huella")
    def huella_script(p: HuellaPedido):
        huella = huella_de(p.codigo)
        return {"huella": huella, "validado_para_real": svc.scripts.validados.esta(huella)}

    # --- calibración ---------------------------------------------------------------------------------------------------------------------
    @app.post("/calibracion/superficie")
    def calibrar_una_superficie(p: SuperficiePedido):
        """Arma la superficie con las esquinas enseñadas (validadas como las del ajedrez) y la deja en la celda en memoria; en el disco solo con `guardar`."""
        brazo = svc.exigir_brazo()
        superficie, avisos = calibrar_superficie(p.nombre, {k: v for k, v in p.puntos.items()}, p.filas, p.columnas, p.z_mm, tuple(p.corrimiento_mm), p.borde_mm)
        brazo.celda.superficies[p.nombre] = superficie
        if p.guardar:
            if not brazo.celda.ruta or "datos" in Path(brazo.celda.ruta).parts:
                raise Conflicto("Esta celda no tiene archivo propio (es la de práctica): la superficie queda solo en memoria")
            guardar_celda(brazo.celda)
        return {"nombre": p.nombre, "z_mm": superficie.z_mm, "esquinas": {k: list(v) for k, v in superficie.esquinas.items()}, "avisos": avisos, "ejemplo": superficie.lugar("a1")}

    @app.post("/calibracion/largo-herramienta")
    def largo_de_la_herramienta(p: LargoPedido):
        if p.poses:
            return calib_herramienta.calibrar_por_pivote(p.poses)
        if p.z_brida_mm is None or p.z_superficie_mm is None:
            raise ValueError("Mandá z_brida_mm y z_superficie_mm (herramienta vertical apoyada) o una lista de «poses» tocando el mismo punto")
        return {"largo_mm": calib_herramienta.largo_por_apoyo(p.z_brida_mm, p.z_superficie_mm)}

    @app.put("/lugares/{nombre}")
    def guardar_lugar(nombre: str, p: LugarPedido):
        """Guarda como lugar con nombre el punto donde está la herramienta ahora (en memoria; en el disco solo con `guardar` y una celda con archivo propio)."""
        brazo = svc.exigir_brazo()
        lugar = brazo.guardar_lugar(nombre, p.z)
        if p.guardar:
            if not brazo.celda.ruta or "datos" in Path(brazo.celda.ruta).parts:
                raise Conflicto("Esta celda no tiene archivo propio (es la de práctica): el lugar queda solo en memoria")
            guardar_celda(brazo.celda)
        return {"lugar": nombre, **lugar}

    # --- panel ------------------------------------------------------------------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    def raiz():
        return FileResponse(PANEL / "index.html")

    @app.get("/ejemplo-06", include_in_schema=False)
    def ejemplo_06():
        archivo = Path(__file__).resolve().parents[2] / "ejemplos" / "06_api_http_desde_javascript.html"
        if not archivo.exists():
            raise ValueError("El ejemplo 06 solo está en una instalación desde el repositorio (pip install -e .)")
        return FileResponse(archivo)

    app.mount("/panel", StaticFiles(directory=PANEL), name="panel")
    return app


def _exigir_ok(resultado: dict) -> None:
    if not resultado["ok"]:
        raise RecorridoProhibido(resultado["problemas"])


app = crear_app()
