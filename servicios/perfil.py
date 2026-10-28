"""Servicio 3 · Gestión de Perfil (nuevo)."""
from flask import Blueprint, g, jsonify

from core.db import conexion, fila
from core.util import ahora, cuerpo_json, requiere_sesion, texto, texto_opcional

bp = Blueprint("perfil", __name__, url_prefix="/api/perfil")


def _perfil(uid):
    u = fila("SELECT id, nombre, apellidos, email, rol, fecha_registro FROM usuarios WHERE id = ?", (uid,))
    p = fila("SELECT telefono, fecha_nacimiento, preferencias FROM perfiles WHERE usuario_id = ?", (uid,)) or {
        "telefono": "", "fecha_nacimiento": "", "preferencias": ""}
    return {"id": u["id"], "nombre": u["nombre"], "apellidos": u["apellidos"], "email": u["email"],
            "rol": u["rol"], "fechaRegistro": u["fecha_registro"], "telefono": p["telefono"],
            "fechaNacimiento": p["fecha_nacimiento"], "preferencias": p["preferencias"]}


@bp.get("")
@requiere_sesion
def obtener():
    return jsonify(_perfil(g.usuario["id"]))


@bp.put("")
@requiere_sesion
def actualizar():
    d = cuerpo_json()
    nombre = texto(d.get("nombre", g.usuario["nombre"]), "nombre", 100)
    apellidos = (texto_opcional(d.get("apellidos"), 100) or "")
    telefono = texto_opcional(d.get("telefono"), 30) or ""
    nacimiento = texto_opcional(d.get("fechaNacimiento"), 10) or ""
    preferencias = texto_opcional(d.get("preferencias"), 500) or ""
    uid = g.usuario["id"]
    with conexion() as c:
        c.execute("UPDATE usuarios SET nombre = ?, apellidos = ? WHERE id = ?", (nombre, apellidos, uid))
        c.execute(
            """INSERT INTO perfiles(usuario_id, telefono, fecha_nacimiento, preferencias, actualizado)
               VALUES (?,?,?,?,?) ON CONFLICT(usuario_id) DO UPDATE SET telefono = excluded.telefono,
               fecha_nacimiento = excluded.fecha_nacimiento, preferencias = excluded.preferencias,
               actualizado = excluded.actualizado""",
            (uid, telefono, nacimiento, preferencias, ahora()),
        )
    return jsonify(_perfil(uid))
