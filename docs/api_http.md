# API HTTP

`python -m brazo_base.servidor` (instalá con `pip install -e ".[servidor]"`) abre la API y el panel en http://127.0.0.1:8000 (documentación interactiva en `/docs`).
Escucha solo en `127.0.0.1`. Desde un navegador solo aceptan llamadas las páginas de `localhost`/`127.0.0.1` y los archivos abiertos con `file://`.
El brazo real exige `"confirmar_real": true` al conectar.

| Método y ruta | Qué hace |
|---|---|
| `POST /conectar` `{destino, celda?, velocidad?, velocidad_simulacion?, confirmar_real?}` | Abre la conexión (simulador por defecto). |
| `POST /habilitar` · `POST /parar` · `POST /limpiar-error` · `POST /desconectar` | Seguridad. `parar` funciona siempre y cancela la tarea en curso. |
| `GET /estado` · `WS /telemetria` | Modo, pose del TCP, ángulos, herramienta, tarea, objetos y puntos para dibujar el brazo (5 veces por segundo). |
| `POST /mover` `{x,y,z,rz?}` o `{punto}` o `{angulos}` | Valida el recorrido; responde **202** y la tarea se sigue en `/estado`. |
| `POST /herramienta` `{accion: abrir\|cerrar\|abrir_a, valor?}` | 202. `cerrar` deja `{"sostiene": true/false}` en `tarea.resultado`. |
| `POST /llevar` `{desde, hasta}` | Pick and place validado (202). |
| `POST /ensayo` `{tipo: mover\|llevar\|articulaciones, ...}` | Devuelve `{ok, problemas, tramos}` sin mover nada. |
| `GET /celda` · `PUT /celda` `{ruta, celda}` | Leer la celda en uso; validar y guardar una (atómico, con `.bak`) sin conexión. |
| `PUT /puntos/{nombre}` `{guardar?}` | Guarda los ángulos actuales como punto con nombre. |
| `POST /simulador/fallo` `{fallo, activo}` | Alarma, colisión, pieza que se cae… (solo simulador). |

Una sola tarea a la vez (409 si hay otra). Errores: `{"error": "qué hacer"}` con 409 (estado incorrecto), 422 (dato inválido o recorrido prohibido,
con `problemas`) y 503 (el brazo o la herramienta no responde). Pendiente: rutinas y consola de scripts (fase 3).
