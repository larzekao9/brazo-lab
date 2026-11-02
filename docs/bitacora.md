# Bitácora

## Fase 1 — núcleo y simulador (2026-11-02)

**Hecho**
- Estructura del paquete `brazo_base` extraída de `chessia-backend` (cliente TCP, pinza DH, zonas, geometría, protocolo del simulador), sin dependencias de ajedrez.
- Celda (`Celda`, `Superficie`, `Objeto`), lectura tolerante a campos desconocidos, guardado atómico con `.bak`, importador de `point.json` (todos los alias).
- Simulador nuevo con mundo genérico (cajas y cilindros, agarre y apilado geométricos, sin PyBullet), fallos provocables, puerto elegido por el sistema.
- Clase `Brazo`: `mover_a`, `mover_relativo`, `mover_articulaciones`, `ir_a`, `agarrar`, `soltar_en`, `llevar`, `parar`, herramienta.
- Ejemplos 01–05 y 41 pruebas en verde sin hardware.

**Errores del ajedrez corregidos**
1. Altura de traslado: ahora la BASE del objeto que se lleva pasa `holgura` sobre el punto más alto (`seguridad/trayectos.py`, con prueba).
2. Poses en el TCP con herramienta vertical (rx=180, ry=0): girar la muñeca no corre la punta (prueba `test_girar_la_muneca_no_corre_la_punta`). Falta definir `Tool` en el controlador (lista del laboratorio).
3. Guardar una celda no pisa datos ajenos (no hay cementerio ni `z_tope` mezclados).
4. Campos desconocidos se ignoran con aviso; guardado atómico con respaldo.
5. Las pruebas usan puerto 0.

**Pendiente / decisiones**
- `ejecutar_rutina` y la consola de scripts (fase 3), API HTTP y panel (fase 2), `calibracion/` (fase 3).
- `celda/celda.json` del laboratorio quedó SIN superficies, lugares ni límites de mesa: no se midieron en este formato. Solo tiene el controlador, la pinza (217 mm, medida del ajedrez) y el punto `descanso` (ángulos de `calibracion_local/brazo.json`). El `z_tope` del tablero (225.6, medido en la brida) menos 217 da 8.6 mm de TCP: verificar en el laboratorio antes de usarlo.
- Los puntos de esquina del ajedrez (a1, h1, a8, h8) son poses de la brida con la pinza ~3° inclinada; no se copiaron.
- El simulador no valida `MovJ` por ángulos contra las mallas ni con la cinemática real del CR5.
- Pendientes del laboratorio: ver sección 9 de `PLAN_BRAZO_BASE.md`.
