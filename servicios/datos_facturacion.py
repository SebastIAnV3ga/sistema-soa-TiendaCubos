"""Servicio 8 · Datos de Facturación (nuevo): datos fiscales de cada usuario."""
import re

from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, EMAIL_RE, cuerpo_json, requiere_sesion, texto, texto_opcional

bp = Blueprint("datos_facturacion", __name__, url_prefix="/api/datos-facturacion")

RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
COLS = """id, rfc, razon_social AS razonSocial, regimen_fiscal AS regimenFiscal,
          codigo_postal AS codigoPostal, email, uso_cfdi AS usoCfdi, predeterminado"""


def predeterminados_de(usuario_id):
    """Datos fiscales a usar al facturar (los marcados, o el primero)."""
    return fila(
        "SELECT * FROM datos_facturacion WHERE usuario_id = ? ORDER BY predeterminado DESC, id LIMIT 1",
        (usuario_id,))


def _leer(d):
    rfc = texto(d.get("rfc"), "rfc", 13).upper()
    if not RFC_RE.match(rfc):
        raise ApiError(400, "El RFC no tiene un formato válido.")
    cp = texto(d.get("codigoPostal"), "codigoPostal", 5)
    if not re.fullmatch(r"\d{5}", cp):
        raise ApiError(400, "El código postal debe tener 5 dígitos.")
    email = texto_opcional(d.get("email"), 120) or ""
    if email and not EMAIL_RE.match(email):
        raise ApiError(400, "El correo de facturación no es válido.")
    return (rfc, texto(d.get("razonSocial"), "razonSocial", 200),
            texto_opcional(d.get("regimenFiscal"), 100) or "", cp, email,
            texto_opcional(d.get("usoCfdi"), 5) or "G03", 1 if d.get("predeterminado") else 0)


def _fijar_predeterminado(c, uid, dato_id):
    c.execute("UPDATE datos_facturacion SET predeterminado = (id = ?) WHERE usuario_id = ?", (dato_id, uid))


@bp.get("")
@requiere_sesion
def listar():
    return jsonify(filas(f"SELECT {COLS} FROM datos_facturacion WHERE usuario_id = ? ORDER BY id", (g.usuario["id"],)))


@bp.post("")
@requiere_sesion
def crear():
    v = _leer(cuerpo_json())
    uid = g.usuario["id"]
    with conexion() as c:
        primero = not c.execute("SELECT 1 FROM datos_facturacion WHERE usuario_id = ?", (uid,)).fetchone()
        did = c.execute(
            """INSERT INTO datos_facturacion(usuario_id, rfc, razon_social, regimen_fiscal, codigo_postal,
                 email, uso_cfdi, predeterminado) VALUES (?,?,?,?,?,?,?,0)""", (uid, *v[:6])).lastrowid
        if v[6] or primero:
            _fijar_predeterminado(c, uid, did)
    return jsonify(fila(f"SELECT {COLS} FROM datos_facturacion WHERE id = ?", (did,))), 201


@bp.put("/<int:id>")
@requiere_sesion
def editar(id):
    v = _leer(cuerpo_json())
    uid = g.usuario["id"]
    with conexion() as c:
        n = c.execute(
            """UPDATE datos_facturacion SET rfc=?, razon_social=?, regimen_fiscal=?, codigo_postal=?,
                 email=?, uso_cfdi=? WHERE id=? AND usuario_id=?""", (*v[:6], id, uid)).rowcount
        if not n:
            raise ApiError(404, "No existen esos datos de facturación.")
        if v[6]:
            _fijar_predeterminado(c, uid, id)
    return jsonify(fila(f"SELECT {COLS} FROM datos_facturacion WHERE id = ?", (id,)))


@bp.delete("/<int:id>")
@requiere_sesion
def eliminar(id):
    with conexion() as c:
        if not c.execute("DELETE FROM datos_facturacion WHERE id = ? AND usuario_id = ?", (id, g.usuario["id"])).rowcount:
            raise ApiError(404, "No existen esos datos de facturación.")
    return jsonify(eliminado=id)
