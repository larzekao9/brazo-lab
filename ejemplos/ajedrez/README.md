# El ajedrez (ChessIA) sobre la plataforma

El ajedrez es la primera aplicación construida sobre `brazo-base` y el ejemplo completo de cómo se usa desde otra aplicación.

- El **planificador** del ajedrez (capturas, enroque, captura al paso, coronación, cementerio) produce pasos `(desde, hasta, tipo de pieza)`.
- La plataforma los ejecuta con `Brazo.ejecutar_pasos` / `comprobar_pasos`, con los perfiles de agarre y la celda que salen de `calibracion_local/brazo.json`
  (`brazo_base.calibracion.ajedrez.celda_de_ajedrez`).
- En el ajedrez, `backend/servicios/brazo/ejecutor_plataforma.py` es el adaptador (`AJEDREZ_MODO_BRAZO=plataforma`); ver `docs/plataforma_brazo.md` de ese repositorio.

Lo que la plataforma le ofrece a una aplicación como ésta:

| Necesidad | API de `brazo-base` |
|---|---|
| Celda desde datos en memoria | `celda_de_ajedrez(datos)` |
| Comprobar todo antes de mover | `Brazo.comprobar_pasos(pasos)` |
| Pick and place por perfiles | `Brazo.ejecutar_pasos(pasos, volver_a)` |
| Distinguir «cerró en el aire» de «se cayó» | `NoAgarro.reintentable` |
| Modo del controlador sin habilitar nada | `Brazo.modo()` |
| Jugar contra el simulador | `Brazo.colocar_objetos_simulados(...)`, `Brazo.punta_simulada(...)` |
