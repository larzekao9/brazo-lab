"""Prueba de conexión SOLO DE LECTURA con el Dobot CR5AS: no lo habilita ni lo mueve.

Se conecta al puerto dashboard (29999) y pide el estado: modo del robot, posición cartesiana, ángulos de las articulaciones y
errores activos. Sirve para comprobar, desde la laptop, que hay red hacia el controlador y que el modo TCP/IP está activo,
antes de usar `Brazo(destino="real")`. No envía `PowerOn`, `EnableRobot`, `MovJ`, `MovL` ni `DO`: es seguro correrlo con el brazo
encendido y con gente cerca.

Antes de correrlo:
  1. Laptop y controlador en la misma red (con cable: la laptop en 192.168.5.x, por ejemplo 192.168.5.100, máscara
     255.255.255.0; el controlador trae 192.168.5.1 por defecto, pero confirmalo en DobotStudio Pro).
  2. En DobotStudio Pro, el robot en modo de control TCP/IP (si no, responde "Control Mode Is Not Tcp").

Uso:
    python herramientas/probar_conexion.py --host 192.168.5.1
    python herramientas/probar_conexion.py --host 192.168.5.1 --puerto 29999 --timeout 3
"""
from __future__ import annotations

import argparse
import socket

# Solo comandos de consulta. Ninguno mueve ni habilita el robot.
COMANDOS_DE_LECTURA = ("RobotMode()", "GetPose()", "GetAngle()", "GetErrorID()")

# Valores de `RobotMode()` según el manual "Dobot TCP/IP Remote Control Interface Guide V4.6.5" (controlador V4, como el CR5AS).
MODOS_DE_ROBOT = {
    1: "inicializando", 2: "freno liberado", 3: "sin energía (apagado)", 4: "desactivado (sin freno puesto)",
    5: "habilitado y libre", 6: "modo arrastre (enseñanza manual)", 7: "ejecutando (proyecto o cola de comandos)",
    8: "movimiento individual (jog, RunTo)", 9: "ALARMA activa (hay que revisar GetErrorID y limpiar con ClearError)",
    10: "en pausa", 11: "colisión detectada",
}


def interpretar_respuesta(respuesta: str) -> dict:
    """Separa una respuesta del dashboard (`ErrorID,{valores},Comando();`) en sus partes.

    Devuelve `{"error_id": int | None, "valores": str, "comando": str, "texto": respuesta limpia}`. Si la respuesta no tiene
    el formato esperado (por ejemplo `Control Mode Is Not Tcp`), `error_id` es `None` y el texto queda tal cual.
    """
    limpio = respuesta.strip().rstrip(";").strip()
    partes = limpio.split(",", 1)
    try:
        error_id = int(partes[0])
    except ValueError:
        return {"error_id": None, "valores": "", "comando": "", "texto": limpio}
    resto = partes[1] if len(partes) > 1 else ""
    valores, _, comando = resto.rpartition(",")
    return {"error_id": error_id, "valores": valores.strip("{} "), "comando": comando, "texto": limpio}


def consultar(host: str, puerto: int = 29999, timeout: float = 3.0, comandos: tuple[str, ...] = COMANDOS_DE_LECTURA) -> dict[str, dict]:
    """Abre una conexión, envía cada comando de lectura y devuelve `{comando: respuesta interpretada}`.

    Raises:
        ValueError: si se intenta enviar un comando que no es de lectura (protección contra mover el robot sin querer).
        OSError: si no se puede conectar (sin red, IP equivocada, controlador apagado, puerto bloqueado).
    """
    prohibidos = [c for c in comandos if c not in COMANDOS_DE_LECTURA]
    if prohibidos:
        raise ValueError(f"Solo se permiten comandos de lectura; no se enviará: {prohibidos}")
    resultados: dict[str, dict] = {}
    with socket.create_connection((host, puerto), timeout=timeout) as conexion:
        conexion.settimeout(timeout)
        for comando in comandos:
            conexion.sendall(comando.encode("ascii"))
            resultados[comando] = interpretar_respuesta(conexion.recv(1024).decode("ascii", errors="replace"))
    return resultados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="192.168.5.1", help="IP del controlador (por defecto 192.168.5.1, la de fábrica)")
    parser.add_argument("--puerto", type=int, default=29999)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    print(f"Conectando a {args.host}:{args.puerto} (solo lectura)...")
    try:
        resultados = consultar(args.host, args.puerto, args.timeout)
    except OSError as error:
        print(f"\nNo se pudo conectar: {error}")
        print("Revisá: cable de red, que la laptop esté en 192.168.5.x, la IP del controlador y que el robot esté encendido.")
        raise SystemExit(1)

    print("\nRespuestas del controlador:")
    for comando, r in resultados.items():
        print(f"  {comando:<14} -> {r['texto']}")
    if any("Control Mode Is Not Tcp" in r["texto"] for r in resultados.values()):
        print("\nEl robot responde pero NO está en modo TCP/IP: activalo en DobotStudio Pro y volvé a correr este script.")
        raise SystemExit(2)
    modo = resultados["RobotMode()"]
    if modo["error_id"] == 0 and modo["valores"].isdigit():
        print(f"\nModo del robot: {MODOS_DE_ROBOT.get(int(modo['valores']), 'desconocido')} ({modo['valores']})")
    print("\nCopiá esta salida completa y pasámela: guardala en docs/bitacora.md.")


if __name__ == "__main__":
    main()
