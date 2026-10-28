"""Servicio 2 · Autenticación (original: Python/FastAPI, servicio-autenticacion).

Mismas rutas y respuestas `{exito, mensaje, datos}`. La "tienda" de usuarios
que el original consultaba por HTTP es ahora el servicio de Registro.
"""
from flask import Blueprint, jsonify, request

from core import seguridad
from core.util import EMAIL_RE, requiere_sesion, usuario_de_sesion
from servicios import registro

bp = Blueprint("autenticacion", __name__, url_prefix="/api/autenticacion")


def _resp(status, exito, mensaje, datos=None):
    r = jsonify(exito=exito, mensaje=mensaje, datos=datos)
    r.headers["Cache-Control"] = "no-store"
    return r, status


def _usuario_publico(u):
    return {"id": u["id"], "correo": u["email"], "nombres": u["nombre"],
            "apellidos": u["apellidos"], "rol": u["rol"]}


@bp.post("/iniciar-sesion")
def iniciar_sesion():
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return _resp(422, False, "solicitud: El JSON enviado no es válido")
    errores = []
    correo, contrasena = cuerpo.get("correo"), cuerpo.get("contrasena")
    if correo is None:
        errores.append("correo: Este campo es obligatorio")
    elif not isinstance(correo, str) or not EMAIL_RE.match(correo.strip()):
        errores.append("correo: Debe de ser un correo electronico válido")
    if contrasena is None:
        errores.append("contrasena: Este campo es obligatorio")
    elif not isinstance(contrasena, str):
        errores.append("contrasena: Debe de ser un texto")
    if errores:
        return _resp(422, False, "; ".join(errores))

    usuario = registro.usuario_por_correo(correo)
    if usuario is None or not seguridad.validar_contrasena(contrasena, usuario["password_hash"]):
        return _resp(401, False, "Usuario o contraseña incorrectos.")

    token = seguridad.crear_token(
        {"id": usuario["id"], "nombre": usuario["nombre"], "rol": usuario["rol"]}
    )
    respuesta, status = _resp(
        200, True, f"Has inciado sesión como {usuario['nombre']}", _usuario_publico(usuario)
    )
    respuesta.set_cookie("token", token, httponly=True, secure=False, samesite="Lax", path="/", max_age=3600)
    return respuesta, status


@bp.get("/validar-sesion")
@requiere_sesion
def validar_sesion():
    from flask import g

    return _resp(200, True, "Sesión válida.", _usuario_publico(g.usuario))


@bp.post("/cerrar-sesion")
def cerrar_sesion():
    token = request.cookies.get("token")
    if token and "error" not in seguridad.validar_token(token):
        seguridad.tokens_invalidos.add(token)
    respuesta, status = _resp(200, True, "Sesión cerrada.")
    respuesta.delete_cookie("token", path="/", httponly=True, samesite="Lax")
    return respuesta, status


@bp.get("/privado")
@requiere_sesion
def ruta_protegida():
    from flask import g

    return _resp(200, True, f"Hola, {g.usuario['nombre']}! Esta ruta esta protegida")
