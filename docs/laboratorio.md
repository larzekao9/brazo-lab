# Llegar al laboratorio y que funcione

La celda `celda/celda.json` se generó a partir de la calibración REAL del ajedrez (`calibracion_local/brazo.json`) y `Brazo.ejecutar_pasos` manda
**exactamente** los mismos comandos que el `EjecutorReal` del ajedrez (lo comprueba `pruebas/test_paridad_ajedrez.py`, comando por comando). Nada de eso se
volvió a medir: lo que funcionó el 2026-10 sigue valiendo.

## Antes de salir (en tu laptop)

```bash
python3 -m venv ~/.venvs/brazo-base && source ~/.venvs/brazo-base/bin/activate
pip install -e ".[servidor,dev]"
pytest -q                                              # 68 pruebas, sin brazo
python herramientas/ensayar_pieza.py e2 e4 p           # las poses que mandaría, zonas y alcance: no conecta con nada
```

## En el laboratorio, en este orden

1. **Red.** Laptop en 192.168.5.x (p. ej. 192.168.5.100, máscara 255.255.255.0), cable al controlador, brazo encendido y en modo de control **TCP/IP** (DobotStudio Pro).
2. **Solo lectura** (no habilita, no mueve):
   ```bash
   python herramientas/probar_conexion.py --host 192.168.5.1
   ```
3. **Comprobar el modelo** (solo lectura). Con el brazo en 4 o 5 posturas distintas (modo arrastre):
   ```bash
   python herramientas/verificar_geometria.py --host 192.168.5.1
   ```
   Si dice «COINCIDEN», el simulador, la validación por ángulos y el dibujo 3D son fieles. Si no, copiá la salida en `docs/bitacora.md`: el brazo real **no se ve
   afectado** (usa el controlador), solo el modelo.
4. **Primer movimiento, lento y con la mano en el botón de paro** (el brazo se enciende y habilita; usá una pieza real en e2):
   ```bash
   python herramientas/mover_pieza.py e2 e4 p --velocidad 10 --confirmo-el-brazo-real
   ```
5. Si todo salió bien, subí la velocidad (la celda guarda la de producción: 50 %) y probá otras piezas (`n`, `r`, `q`, `k`), el cementerio (`d8 cementerio:3 q`) y la reserva.
6. **Panel**: `python -m brazo_base.servidor` y en el panel elegí «Brazo real» (marca de confirmación y celda `celda/celda.json`).

## Qué hace el brazo en cada paso (igual que el ajedrez)

Abre a la apertura del perfil → va sobre el origen (articular) → baja despacio hasta la altura de agarre → cierra y comprueba que sostiene algo → sube despacio y
vuelve a comprobar → se traslada sobre el destino → baja despacio → suelta (más abierta) → sube despacio → al final, vuelve al punto `descanso` por ángulos.
Si cierra en el aire (no hay pieza) o se le cae, se detiene con un mensaje que dice qué revisar.

## Qué NO está comprobado hasta que lo hagas en el laboratorio

- Que los ángulos del controlador coincidan con el URDF (paso 3). Afecta al simulador, a la validación de movimientos por ángulos del usuario y al dibujo.
- El TCP «de verdad» (definir la herramienta en el controlador con `SetTool`): mientras tanto la celda usa el modo `brida`, el que ya funcionó. Medí el largo de la pinza y
  probá `SetTool` cuando quieras pasar al modo `tcp` (poses en la punta, giros de muñeca sin correr la punta).
- `InverseSolution`, las medidas de la mesa y las otras herramientas (lista de la sección 9 de `PLAN_BRAZO_BASE.md`).

Si algo falla, el brazo se detiene con `Stop()` y el error dice qué hacer; el botón de paro físico siempre manda.
