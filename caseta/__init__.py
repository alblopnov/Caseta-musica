"""Caseta: a fair, shared music queue for a Raspberry Pi jukebox."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from caseta.config import Config
from caseta.engine import PlaybackEngine
from caseta.fair_queue import FairQueue
from caseta.identity import AdminAuth, init_identity
from caseta.library import Library
from caseta.player import Player
from caseta.portal import init_portal

_ROOT = Path(__file__).resolve().parent.parent


def create_app(
    config: Config | None = None,
    player: Player | None = None,
    start_engine: bool = True,
) -> Flask:
    from caseta.routes import _register_domain_handlers, bp, register_http_error_handlers

    config = config or Config.from_env()
    if player is None:
        from caseta.player import PygamePlayer

        player = PygamePlayer()

    app = Flask(
        __name__,
        template_folder=str(_ROOT / "templates"),
        static_folder=str(_ROOT / "static"),
    )
    app.secret_key = config.secret_key
    app.config["MAX_CONTENT_LENGTH"] = config.max_upload_bytes  # the only upload size bound
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    library = Library(config)
    engine = PlaybackEngine(FairQueue(config.max_pending_per_user), player, library)
    app.extensions["config"] = config
    app.extensions["library"] = library
    app.extensions["engine"] = engine
    app.extensions["admin_auth"] = AdminAuth(config.admin_pin)

    init_portal(app, config)  # before identity: redirected requests get no cookie
    init_identity(app)
    _register_domain_handlers(app)
    register_http_error_handlers(app)
    app.register_blueprint(bp)

    if start_engine:
        engine.start()
    return app
