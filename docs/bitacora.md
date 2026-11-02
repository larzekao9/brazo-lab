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

## Fase 2 — API HTTP y panel (2026-11-02)

**Hecho**
- `brazo_base/servidor/`: FastAPI con todas las rutas de la sección 7 del plan salvo rutinas y scripts; una tarea a la vez (hilo), 202 y seguimiento en `/estado`; `parar` cancela la tarea.
- `Brazo.ensayo()` (y `/ensayo`) devuelve el plan y los problemas sin mover nada; `/mover` y `/llevar` validan de forma síncrona antes de responder 202.
- Telemetría por WebSocket con los puntos para dibujar el brazo (modelo esquemático en el simulador, URDF en el real).
- Panel web sin compilar (HTML + Three.js): conexión, vista 3D de la celda, mover a mano, herramienta, puntos, llevar con ensayo, fallos. Comprobado en un navegador contra el simulador.
- Seguridad: solo `127.0.0.1`, CORS limitado a orígenes locales, `confirmar_real` obligatorio para el real.
- Ejemplo 06 (página que mueve el brazo por HTTP) y `docs/api_http.md`. 60 pruebas sin hardware.

**Pendiente / decisiones**
- El panel no es React (el plan lo sugería): se eligió HTML + módulos ES para que un estudiante lo pueda leer y cambiar sin `npm`. Si se quiere React, la API no cambia.
- Falta en el panel: mover por articulaciones, rutinas y la consola de scripts (fase 3), y los modelos 3D reales del CR5 (hoy es un esqueleto de líneas y esferas).
- Los puntos guardados con el panel quedan en memoria; solo se escriben a disco con `guardar` y una celda con archivo propio.

### Animaciones del panel (2026-11-02)
- La telemetría sube a 10 Hz y el panel interpola entre muestras con GSAP 3.12.5 (cdnjs): el brazo y los objetos se mueven sin saltos. Las mallas se crean una vez y solo se actualizan sus posiciones.
- Botones de vista de cámara (3/4, arriba, lateral, frente) con transición; mensajes que entran y salen con fundido; la insignia de estado hace un pulso al cambiar.
- Todo respeta `prefers-reduced-motion` (salta directo, sin transiciones).
- Buenas prácticas tomadas de los skills de GSAP del repo Neverita (`quickTo`/`overwrite`, `autoAlpha`, `matchMedia`). De ese repo no se copió código al proyecto.
- Bug encontrado probando en el navegador: dos `gsap.to` con `overwrite: true` sobre el mismo objeto se cancelan entre sí; se usa `overwrite: "auto"`.

## Calibración real y equivalencia con el ajedrez (2026-11-02)

**Hecho**
- `celda/celda.json` sale de `calibracion_local/brazo.json` (solo se lee): orientación enseñada, tablero (ajuste afín por mínimos cuadrados igual que el ajedrez, corrimiento y marco),
  6 perfiles de agarre (peón a rey), cementerio, cementerio del jugador y reserva, velocidades y la pinza (217 mm, fuerza 43, velocidad 20).
- Modo `brida`: las poses se mandan tal cual con la orientación enseñada. `Brazo.ejecutar_pasos` / `llevar_desde` replican la secuencia de `EjecutorReal`. **Prueba de equivalencia:**
  10 jugadas (borde, cementerio con desnivel, cementerio del jugador, reserva) dan los mismos comandos que el ajedrez; 5 quedaron congeladas en `pruebas/datos/` como regresión.
- Simulador con cinemática del URDF y cinemática inversa numérica (antes esquemática): sus ángulos son los de un CR5, no los de un modelo inventado. `MovL` sigue la recta de verdad.
- `mover_a` elige `MovJ` o `MovL` (giro grande o recta cerca de la base → articular); `mover_relativo` conserva la orientación; `ir_a` a una pose enseñada va exactamente a ella.
- `Herramienta.preparar()`: la pinza solo se mueve al conectar si no estaba inicializada (como `EjecutorReal.conectar`).
- Scripts de laboratorio y `docs/laboratorio.md`.

**Descubierto**
- En TCP vertical la punta quedaría ~12 mm fuera de donde calibró el ajedrez (la inclinación de 2,4° y el giro de 45°): por eso la celda del laboratorio usa `brida`.
- Corregido sin cambiar los valores del laboratorio: la altura de traslado ya no resta el margen de agarre (con esta calibración da lo mismo: 90 mm).

**Pendiente**
- Verificar en el laboratorio que el URDF coincide con los ángulos del controlador (`herramientas/verificar_geometria.py`).
- Rutinas guardadas del ajedrez copiadas a `celda/rutinas/` (formato del ajedrez); falta el ejecutor de rutinas (fase 3).
- El planificador del ajedrez (capturas, enroque…) sigue en el ajedrez; produce pasos `(desde, hasta, perfil)` para `ejecutar_pasos` (fase 5).
