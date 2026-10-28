"""Servicio 7 · Direcciones de Envío (original: C# minimal API + SQL Server)."""
from flask import Blueprint, g, jsonify, request

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, usuario_de_sesion

bp = Blueprint("direcciones", __name__, url_prefix="/api/direcciones")

COLUMNAS = """id, usuario_id AS usuarioId, calle, numero, colonia, ciudad, estado,
              codigo_postal AS codigoPostal, referencia, fecha_creacion AS fechaCreacion"""


@bp.before_request
def _proteger():
    usuario = usuario_de_sesion()
    if usuario is None:
        raise ApiError(401, "No has iniciado sesión.")
    g.usuario = usuario


@bp.errorhandler(ApiError)
def _errores(e):
    return jsonify(mensaje=str(e)), e.status  # este servicio responde {mensaje} como el original


def _ajena(usuario_id):
    return g.usuario["rol"] != "admin" and usuario_id != g.usuario["id"]


def _nulo(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def _validar(d):
    uid = d.get("usuarioId")
    if type(uid) is not int or uid <= 0:
        return "El ID de usuario debe ser un número mayor a 0."
    obligatorios = (("calle", "La calle es obligatoria."), ("ciudad", "La ciudad es obligatoria."),
                    ("estado", "El estado es obligatorio."))
    for campo, mensaje in obligatorios:
        v = d.get(campo)
        if not isinstance(v, str) or not v.strip():
            return mensaje
    return None


def obtener_direccion(did):
    return fila(f"SELECT {COLUMNAS} FROM direcciones WHERE id = ?", (did,))


@bp.post("")
def registrar():
    d = cuerpo_json()
    error = _validar(d)
    if error:
        return jsonify(mensaje=error), 400
    if _ajena(d["usuarioId"]):
        return jsonify(mensaje="Solo puedes registrar direcciones a tu nombre."), 403
    with conexion() as c:
        nuevo = c.execute(
            """INSERT INTO direcciones(usuario_id, calle, numero, colonia, ciudad, estado, codigo_postal,
                 referencia, fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?)""",
            (d["usuarioId"], d["calle"].strip(), _nulo(d.get("numero")), _nulo(d.get("colonia")),
             d["ciudad"].strip(), d["estado"].strip(), _nulo(d.get("codigoPostal")),
             _nulo(d.get("referencia")), ahora()),
        ).lastrowid
    return jsonify(mensaje=f"Dirección registrada correctamente (ID {nuevo}).", id=nuevo)


@bp.get("")
def listar():
    uid = request.args.get("usuarioId", type=int)
    if g.usuario["rol"] != "admin":
        uid = g.usuario["id"]  # un cliente solo ve sus direcciones
    if uid is not None:
        return jsonify(filas(f"SELECT {COLUMNAS} FROM direcciones WHERE usuario_id = ? ORDER BY id", (uid,)))
    return jsonify(filas(f"SELECT {COLUMNAS} FROM direcciones ORDER BY id"))


@bp.get("/<int:id>")
def consultar(id):
    d = obtener_direccion(id)
    if not d or _ajena(d["usuarioId"]):
        return jsonify(mensaje=f"No existe una dirección con el ID {id}."), 404
    return jsonify(d)


@bp.put("/<int:id>")
def editar(id):
    d = cuerpo_json()
    error = _validar(d)
    if error:
        return jsonify(mensaje=error), 400
    actual = obtener_direccion(id)
    if actual and _ajena(actual["usuarioId"]):
        actual = None
    if not actual:
        return jsonify(mensaje=f"No existe una dirección con el ID {id}."), 404
    with conexion() as c:
        n = c.execute(
            """UPDATE direcciones SET calle=?, numero=?, colonia=?, ciudad=?, estado=?, codigo_postal=?,
                 referencia=? WHERE id=?""",
            (d["calle"].strip(), _nulo(d.get("numero")), _nulo(d.get("colonia")), d["ciudad"].strip(),
             d["estado"].strip(), _nulo(d.get("codigoPostal")), _nulo(d.get("referencia")), id),
        ).rowcount
    if n == 0:
        return jsonify(mensaje=f"No existe una dirección con el ID {id}."), 404
    return jsonify(mensaje=f"Dirección {id} actualizada correctamente.")
