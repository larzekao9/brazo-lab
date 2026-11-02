"""`python -m brazo_base.servidor` arranca la API y el panel en http://127.0.0.1:8000"""
import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor HTTP y panel de brazo-base")
    parser.add_argument("--host", default="127.0.0.1", help="Por defecto solo escucha en este equipo (127.0.0.1)")
    parser.add_argument("--puerto", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("brazo_base.servidor.api:app", host=args.host, port=args.puerto)


if __name__ == "__main__":
    main()
