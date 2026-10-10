"""Production entry point: serves the Caseta jukebox with waitress."""
from __future__ import annotations

import os
import sys

import waitress

from caseta import create_app
from caseta.config import Config


def _port(raw: str | None) -> int:
    if raw is None or raw.strip() == "":
        return 5000
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"CASETA_PORT must be an integer, got {raw!r}") from None


def main() -> None:
    try:
        config = Config.from_env()
        port = _port(os.environ.get("CASETA_PORT"))
    except ValueError as error:
        print(f"Configuración inválida: {error}", file=sys.stderr)
        sys.exit(2)
    if not config.admin_pin:
        print("Aviso: CASETA_ADMIN_PIN no está definido; la página de administración está desactivada.", file=sys.stderr)

    app = create_app(config)
    engine = app.extensions["engine"]
    try:
        waitress.serve(app, host="0.0.0.0", port=port, threads=8)
    finally:
        engine.stop()  # first, so the engine cannot start another song...
        engine.skip()  # ...then silence the one still playing


if __name__ == "__main__":
    main()
