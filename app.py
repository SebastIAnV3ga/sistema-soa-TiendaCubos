"""Sistema SOA de comercio electrónico · GESE CUBES.

Un solo proceso Python (Flask) que aloja los servicios como módulos
independientes (cada uno es un Blueprint con su propio prefijo /api/<servicio>)
y sirve el portal web con el diseño unificado.

    python app.py            ->  http://127.0.0.1:5001
"""
import os

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from core import db
from core.util import ApiError
import servicios


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.json.ensure_ascii = False
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000
    db.iniciar()
    servicios.registrar(app)

    @app.get("/")
    def portal():
        return app.send_static_file("index.html")

    @app.get("/api/salud")
    def salud():
        db.fila("SELECT 1")
        return jsonify({"estado": "ok"})

    @app.after_request
    def cabeceras(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if "/api/" in (resp.headers.get("Location") or "") or resp.mimetype == "application/json":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.errorhandler(ApiError)
    def api_error(e):
        return jsonify({"error": str(e), **e.extra}), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify({"error": e.description}), e.code

    @app.errorhandler(Exception)
    def error_interno(e):
        app.logger.exception(e)
        return jsonify({"error": "Error interno del servidor"}), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5001")),
            debug=os.getenv("DEBUG") == "1", threaded=True)
