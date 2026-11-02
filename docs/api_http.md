# API HTTP

`python -m brazo_base.servidor` (instalá con `pip install -e ".[servidor]"`) abre la API y el panel en http://127.0.0.1:8000 (documentación interactiva en `/docs`).
Escucha solo en `127.0.0.1`. Solo aceptan llamadas las páginas servidas desde `localhost`/`127.0.0.1`: un pedido que cambia algo y trae un `Origin` de otro sitio
(o `null`, el de un archivo `file://`) se rechaza con 403 aunque el navegador no haga preflight. Cualquier programa de tu equipo sí puede usar la API (es una herramienta de
laboratorio): la consola de scripts ejecuta código de Python con tus permisos. El brazo real exige `"confirmar_real": true` al conectar.

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
| `PUT /lugares/{nombre}` `{z?, guardar?}` | Guarda como lugar el punto donde está la herramienta («guardar un lugar llevando el brazo»). |
| `POST /agarrar` `{objeto}` · `POST /soltar` `{lugar}` · `POST /llevar-desde` `{desde, hasta, perfil, volver_a}` | Pick and place por partes o por perfiles de agarre (202). |
| `GET /rutinas` · `GET/PUT/DELETE /rutinas/{nombre}` | Rutinas (pasos con nombre). `PUT` valida cada pose, los saltos y los ciclos. |
| `POST /rutinas/{nombre}/ejecutar` `{factor, confirmar}` | 202. Todo lo comprobable se responde antes de mover. En el real exige que esté validada y `confirmar`. |
| `POST /scripts/ejecutar` `{codigo, confirmar?, limite_segundos?}` | Corre el script en un proceso aparte (202). El script ve `brazo`, que le pide todo a este servidor. |
| `GET /scripts/estado?desde=N` · `POST /scripts/parar` · `POST /scripts/huella` | Salida en vivo, estado y parada; la huella dice si el código está validado para el real. |
| `POST /calibracion/superficie` `{nombre, puntos, filas, columnas, ...}` | Superficie con cuadrícula desde 3 o 4 esquinas enseñadas (validadas como las del ajedrez). |
| `POST /calibracion/largo-herramienta` `{z_brida_mm, z_superficie_mm}` o `{poses}` | Largo de la herramienta por apoyo, o por pivote con varias poses tocando el mismo punto. |
| `POST /simulador/fallo` `{fallo, activo}` | Alarma, colisión, pieza que se cae… (solo simulador). |

Una sola tarea a la vez (409 si hay otra). Errores: `{"error": "qué hacer"}` con 409 (estado incorrecto), 422 (dato inválido o recorrido prohibido,
con `problemas`) y 503 (el brazo o la herramienta no responde).
