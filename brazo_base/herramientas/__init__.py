from brazo_base.herramientas.base import Herramienta
from brazo_base.herramientas.ninguna import SinHerramienta
from brazo_base.herramientas.pinza_dh import PinzaDHHerramienta
from brazo_base.herramientas.salida_digital import SalidaDigital


def herramienta_desde_config(config: dict, nombre: str) -> Herramienta:
    """Arma la herramienta que describe el JSON de `celda/herramientas/<nombre>.json` (campo `tipo`)."""
    tipo = config.get("tipo", "ninguna")
    if tipo == "ninguna":
        return SinHerramienta()
    if tipo == "pinza_dh":
        return PinzaDHHerramienta(config.get("largo_mm", 217.0), int(config.get("fuerza", 20)), int(config.get("velocidad", 20)), config.get("carrera_mm", 26.0), nombre, config.get("modelo_3d"))
    if tipo == "salida_digital":
        return SalidaDigital(int(config["pin"]), config.get("largo_mm", 0.0), nombre, config.get("modelo_3d"))
    raise ValueError(f"Tipo de herramienta desconocido «{tipo}» en «{nombre}». Tipos: ninguna, pinza_dh, salida_digital")


__all__ = ["Herramienta", "SinHerramienta", "PinzaDHHerramienta", "SalidaDigital", "herramienta_desde_config"]
