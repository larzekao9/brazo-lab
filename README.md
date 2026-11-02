# brazo-base

Plataforma abierta para **aprender, practicar y desarrollar** con el brazo Dobot CR5AS del laboratorio **sin tener el brazo delante**. Lo que
funciona en el simulador funciona igual en el brazo real: solo cambia `destino`.

> Estado: **fase 1** (núcleo + simulador + librería `Brazo`). Ver `docs/bitacora.md` y `../Ajedrez/PLAN_BRAZO_BASE.md`.

## Instalación

```bash
python3 -m venv ~/.venvs/brazo-base && source ~/.venvs/brazo-base/bin/activate
pip install -e ".[dev]"
```

Creá el entorno virtual **fuera** de la carpeta del proyecto si ésta está en el Escritorio o Documentos de macOS (iCloud marca los archivos `.pth`
como «hidden» y Python 3.13+ los ignora: `import brazo_base` falla aunque `pip` diga que se instaló).

## Tu primer script (10 minutos)

```python
from brazo_base import Brazo

with Brazo() as brazo:                       # simulador por defecto
    brazo.llevar("caja_roja", "bandeja")      # agarra, sube, traslada, suelta
    brazo.mover_a(x=0, y=-500, z=150)         # mm, en la punta de la herramienta
```

```bash
python ejemplos/05_pick_and_place.py
pytest            # todas las pruebas corren sin brazo
```

## Reglas que no se rompen

- **El simulador es el destino por defecto.** El brazo real solo se toca con `Brazo(destino="real", celda="celda/celda.json")`.
- **Nada se mueve sin validar antes** el recorrido completo: límites de la mesa, zonas prohibidas, altura mínima y límites de articulación.
- Las poses están en el **TCP** (punta de la herramienta), con la herramienta vertical.
- El simulador habla el mismo protocolo TCP que el controlador V4 y `Brazo` lo usa con el mismo cliente que el real.

## Estructura

| Carpeta | Qué hay |
|---|---|
| `brazo_base/brazo.py` | La clase `Brazo` (API pública) |
| `brazo_base/celda/` | Modelo de la celda, archivo JSON (atómico, con `.bak`), importador de DobotStudio |
| `brazo_base/seguridad/` | Zonas, geometría del CR5 (URDF), validador, alturas de viaje |
| `brazo_base/herramientas/` | Interfaz `Herramienta`, pinza DH, salida digital, ninguna |
| `brazo_base/simulador/` | Controlador virtual (protocolo V4, pinza Modbus, fallos provocables) |
| `celda/` | La configuración de ESTA celda del laboratorio (a completar en el laboratorio) |
| `ejemplos/` | Scripts 01 a 05 |

## Limitaciones conocidas del simulador

La cinemática es **esquemática** (herramienta vertical, sin límites reales de articulación) y no hay choques del brazo contra objetos: solo las
zonas prohibidas y los límites de la mesa. Los ángulos del simulador no coinciden con los del CR5 real; las poses (x, y, z) sí.

Fallos para practicar: `brazo.simulador.provocar("alarma" | "colision" | "no_tcp" | "pinza_no_responde" | "pieza_cae")`.

## Licencia

MIT (confirmar con los coautores antes de publicar).
