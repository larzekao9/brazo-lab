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

### Modelo 3D real del brazo (2026-11-02)
- El panel carga el `dobot_cr5.glb` (CAD oficial, el del ajedrez, copiado a `servidor/panel/modelos/`; el decodificador Draco se baja de unpkg) con la pinza DH (cuerpo y dos dedos que siguen el ancho real). El esqueleto queda solo de respaldo si el modelo no carga.
- **El simulador y el dibujo usan la misma geometría, la del GLB** (antes: un modelo esquemático y, después, el URDF del proyecto). Medido en el navegador: las 6 articulaciones del modelo 3D coinciden con la cinemática del servidor a ≤ 0,065 mm y la punta de la pinza cae a 0,06 mm de la punta calculada.
- **Por qué se dejó el URDF para la cinemática:** el URDF del proyecto pone la brida apuntando hacia ARRIBA en pose cero (la estructura estándar de los CR es de lado) y con él tus ángulos reales no tenían sentido (el descanso real daba la herramienta en una dirección rara y el tablero pedía J5 entre 8° y 134°). Con la geometría del CAD: el descanso real (J5 = 90,45°) deja la herramienta apuntando recto hacia abajo, y las 4 esquinas del tablero salen con J5 ≈ 90°. Eso apoya el modelo, pero **no lo prueba**: falta `herramientas/verificar_geometria.py` en el laboratorio.
- Los otros dos modelos disponibles (URDF oficial de ROS del CR5 y el URDF del proyecto) tienen desfases laterales distintos entre sí y del GLB; si el laboratorio da diferencias, el lugar a tocar es `ORIGENES`/`EJES` en `simulador/cinematica.py` (y `MAPA_GLB`, que fija hacia dónde mira la base).
- `seguridad/geometria.py` (URDF) sigue validando los movimientos por ángulos que da el usuario (`mover_articulaciones`). Con el brazo real, los ángulos de `ir_a` a un punto enseñado NO pasan por esa validación.
- Con el brazo real el panel mueve el GLB con los ángulos del controlador (como el front del ajedrez); si el modelo no coincidiera con el brazo, el dibujo se vería mal pero el brazo no se afecta.
- Los archivos del panel se sirven con `Cache-Control: no-cache` (un navegador se quedaba con el JS viejo tras actualizar).

## Fase 3 — rutinas, consola de scripts y calibración (2026-11-02)

**Hecho**
- **Rutinas** (`brazo_base/rutinas/`): portadas del ajedrez con su mismo formato (las 3 rutinas reales ya cargan desde `celda/rutinas/`), con validación de cada pose, de los saltos entre poses (150°), de los ciclos y de la huella. `Brazo.ejecutar_rutina` y `comprobar_rutina` (todo lo comprobable antes de mover): en el simulador corre y queda validada; en el real exige validación y confirmación, topa la velocidad y no mueve nada si una pose cae en una zona prohibida.
- **Consola de scripts** (`brazo_base/scripts/`): el script corre en un proceso aparte, con tiempo límite y salida en vivo, pero NO se conecta al brazo: usa `BrazoRemoto`, que le pide todo al servidor por HTTP (la plataforma sigue siendo la única dueña del brazo, así que zonas, validaciones y el botón de parar siguen valiendo). En el real solo corre si terminó sin errores en el simulador con exactamente ese código (huella) y con confirmación.
- **Asistentes de calibración** (`brazo_base/calibracion/`): superficie desde 3 o 4 esquinas con las validaciones del ajedrez (orientación, altura, residuos) y una más que faltaba (esquinas casi colineales sobre la mesa); largo de herramienta por apoyo o por pivote; `Brazo.guardar_lugar`.
- **API y panel**: rutas de rutinas, scripts, calibración, `/agarrar`, `/soltar` y `/llevar-desde`; en el panel, las secciones Rutinas, Consola de scripts y Calibración. Probado de punta a punta en un navegador: se arma y guarda una rutina, se ejecuta y queda «✓ validada»; un script mueve el brazo y muestra su salida en vivo; se capturan 3 esquinas y se dibuja la superficie nueva.
- `herramientas/verificar_geometria.py` ahora usa `PositiveKin` (no mueve el brazo) en 7 posturas, y si hay diferencia dice si es solo un giro de la base (tomado de `verificar_geometria` del ajedrez).
- 147 pruebas sin hardware; los scripts se prueban contra un servidor HTTP real.

**Encontrado y corregido**
- **Seguridad (al agregar una ruta que ejecuta código):** el servidor aceptaba pedidos «simples» de cualquier página abierta en el navegador, que pueden saltarse el preflight de CORS. Ahora rechaza con 403 todo pedido que cambia algo y trae un `Origin` que no es de localhost (incluido `null`), y `file://` ya no puede llamar a la API (el ejemplo 06 se sirve desde `/ejemplo-06`).
- Tras **Parar**, la tarea en curso tardaba hasta ~1 s en darse por terminada: `esperar_fin` no miraba si se canceló. Ahora termina al instante con «Cancelado por el usuario».
- Una superficie calibrada con 3 esquinas (sin `h8`) hacía fallar el dibujo del panel: la cuarta esquina se completa como paralelogramo.
- Una superficie con las tres esquinas casi sobre una recta pasaba la validación: ahora se rechaza.

**Pendiente / decisiones**
- La consola ejecuta código de Python con los permisos del usuario (no hay sandbox). Es una herramienta de laboratorio en el equipo del usuario; cualquier programa de ese equipo puede usar la API. Si algún día se expone en red, hace falta autenticación.
- El editor de la consola es un `textarea` (sin resaltado ni autocompletado).
- Las rutinas se guardan por celda (`rutinas/` junto a su archivo); con la celda de práctica, en `~/.brazo-base/rutinas`.
- `calibrar_por_pivote` depende de la convención de Euler (`Rz·Ry·Rx`) sin verificar contra DobotStudio: `herramientas/verificar_geometria.py` la comprueba.
- Sigue sin probarse nada de esto con el brazo real.
