# Una aplicación sobre la plataforma (ejemplo: el ajedrez)

El proyecto de ajedrez (ChessIA) es la aplicación que dio origen a la plataforma y sigue usando su propio código del brazo: **esta plataforma no lo modifica ni depende de él**.

Para que una aplicación como esa use `brazo-base`, la plataforma ofrece:

| Necesidad | API de `brazo-base` |
|---|---|
| Celda desde datos en memoria | `celda_de_ajedrez(datos)` (o `celda_desde_dict`) |
| Comprobar todo antes de mover | `Brazo.comprobar_pasos(pasos)` |
| Pick and place por perfiles | `Brazo.ejecutar_pasos(pasos, volver_a)` |
| Distinguir «cerró en el aire» de «se cayó» | `NoAgarro.reintentable` |
| Modo del controlador sin habilitar nada | `Brazo.modo()` |
| Jugar contra el simulador | `Brazo.colocar_objetos_simulados(...)`, `Brazo.punta_simulada(...)` |

La equivalencia de la secuencia de agarre con la del ajedrez está comprobada comando por comando en `pruebas/test_paridad_ajedrez.py`.
