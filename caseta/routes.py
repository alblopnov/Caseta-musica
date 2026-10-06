"""HTTP API for the fair shared queue. Every API error is ``{"error", "code"}`` JSON."""
from __future__ import annotations

import re

from flask import Blueprint, current_app, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from caseta.song_queue import DuplicateSong, NotOwner, QueueFull, UnknownItem
from caseta.identity import is_admin, set_admin
from caseta.library import InvalidUpload, SongNotFound

bp = Blueprint("caseta", __name__)

_TRUTHY = {"1", "true"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


def error_response(status: int, code: str, message: str, **extra):
    return jsonify({"error": message, "code": code, **extra}), status


def _domain_error(exc: Exception) -> ApiError | None:
    """Translate an engine/library exception into the API error it stands for."""
    if isinstance(exc, SongNotFound):
        return ApiError(404, "not_found", "Esa canción no existe.")
    if isinstance(exc, UnknownItem):
        return ApiError(404, "not_found", "Esa canción ya no está en la cola.")
    if isinstance(exc, DuplicateSong):
        return ApiError(409, "duplicate", "Esa canción ya está en la cola.")
    if isinstance(exc, QueueFull):
        cap = current_app.extensions["config"].max_pending_per_user
        return ApiError(409, "full", f"Ya tienes {cap} canciones en la cola. Espera a que suene alguna.")
    if isinstance(exc, NotOwner):
        return ApiError(403, "forbidden", "Solo puedes quitar tus propias canciones.")
    if isinstance(exc, InvalidUpload):
        return ApiError(400, "bad_request", "Archivo no válido. Solo se admiten mp3, wav y ogg.")
    return None


@bp.app_errorhandler(ApiError)
def _handle_api_error(e: ApiError):
    return error_response(e.status, e.code, e.message, **e.extra)


def _register_domain_handlers(app) -> None:
    def handler(exc):
        err = _domain_error(exc)
        return error_response(err.status, err.code, err.message, **err.extra)

    for cls in (SongNotFound, UnknownItem, DuplicateSong, QueueFull, NotOwner, InvalidUpload):
        app.register_error_handler(cls, handler)


# -- helpers ----------------------------------------------------------------


def json_object() -> dict:
    try:
        body = request.get_json(silent=True)
    except RecursionError:  # absurdly nested JSON: json.loads gives up, silent=True does not catch it
        body = None
    if not isinstance(body, dict):
        raise ApiError(400, "bad_request", "La petición no es válida.")
    return body


def require_admin() -> None:
    if not is_admin():
        raise ApiError(401, "unauthorized", "Necesitas ser administrador.")


def _engine():
    return current_app.extensions["engine"]


def _library():
    return current_app.extensions["library"]


def _item_json(item) -> dict:
    return {"id": item.id, "song": item.song, "title": _library().title(item.song)}


# -- pages --------------------------------------------------------------------


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/albertitoeselmejor")
def admin_page():
    return render_template("admin.html")


# -- queue ------------------------------------------------------------------------


@bp.get("/api/songs")
def songs():
    return jsonify(_library().list_songs())


@bp.get("/api/state")
def state():
    return jsonify(_engine().snapshot(g.client_id))


@bp.post("/api/queue")
def enqueue():
    song = json_object().get("song")  # any "position" field is deliberately ignored
    if not isinstance(song, str):
        raise ApiError(400, "bad_request", "Falta el nombre de la canción.")
    item = _engine().enqueue(song, g.client_id)
    return jsonify(_item_json(item)), 201


@bp.delete("/api/queue/<item_id>")
def remove(item_id: str):
    _engine().remove(item_id, g.client_id, is_admin())
    return jsonify({"status": "removed"})


@bp.post("/api/queue/<item_id>/move")
def move(item_id: str):
    require_admin()
    position = json_object().get("position")
    if not isinstance(position, int) or isinstance(position, bool):
        raise ApiError(400, "bad_request", "La posición debe ser un número entero.")
    _engine().move(item_id, position)
    return jsonify({"status": "moved"})


@bp.post("/api/skip")
def skip():
    require_admin()
    _engine().skip()
    return jsonify({"status": "skipped"})


# -- upload -------------------------------------------------------------------------


@bp.post("/api/upload")
def upload():
    file = request.files.get("song")
    if file is None or not file.filename:
        raise ApiError(400, "bad_request", "Elige un archivo de audio.")
    song = _library().save_upload(file)  # InvalidUpload -> 400 via the domain handler
    item = None
    if request.form.get("enqueue", "").strip().lower() in _TRUTHY:
        try:
            item = _engine().enqueue(song, g.client_id)
        except (QueueFull, DuplicateSong) as e:
            err = _domain_error(e)  # the file stays saved; tell the client where
            return error_response(err.status, err.code, err.message, song=song)
    return jsonify({"song": song, "item": _item_json(item) if item else None}), 201


# -- admin --------------------------------------------------------------------------


@bp.post("/api/admin/login")
def admin_login():
    pin = json_object().get("pin")  # raw JSON value: AdminAuth tolerates anything
    key = request.remote_addr or "unknown"
    result = current_app.extensions["admin_auth"].attempt(pin, key)
    if result == "ok":
        set_admin(True)
        return jsonify({"admin": True})
    if result == "locked":
        raise ApiError(429, "locked", "Demasiados intentos. Espera un minuto.")
    if result == "disabled":
        raise ApiError(503, "admin_disabled", "El modo administrador no está activado.")
    raise ApiError(401, "bad_pin", "PIN incorrecto.")


@bp.get("/api/admin/session")
def admin_session():
    return jsonify({"admin": is_admin()})


# -- JSON error pages for /api/ -----------------------------------------------------------

_HTTP_ERRORS = {
    400: ("bad_request", "La petición no es válida."),
    404: ("not_found", "No encontrado."),
    405: ("method_not_allowed", "Método no permitido."),
    413: ("too_large", "El archivo es demasiado grande."),
    500: ("server_error", "Error interno del servidor."),
}


def _is_api_path() -> bool:
    return request.path == "/api" or request.path.startswith("/api/")


def register_http_error_handlers(app) -> None:
    def make(status: int):
        code, message = _HTTP_ERRORS[status]

        def handler(e: HTTPException):
            if _is_api_path():
                return error_response(status, code, message)
            return e  # non-API pages keep Flask's default response

        return handler

    for status in _HTTP_ERRORS:
        app.register_error_handler(status, make(status))

    def generic(e: HTTPException):
        status = e.code
        if not _is_api_path() or status is None or status < 400:  # redirects etc. pass through
            return e
        slug = re.sub(r"[^a-z0-9]+", "_", e.name.lower()).strip("_") or "error"
        return error_response(status, slug, "La petición no se pudo completar.")

    app.register_error_handler(HTTPException, generic)
