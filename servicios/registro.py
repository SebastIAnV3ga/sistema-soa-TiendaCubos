"""Servicio 1 · Registro de Usuarios (original: Node/Express, ServicioRegistroUsuarios)."""
from flask import Blueprint, jsonify

from core import seguridad
from core.db import ejecutar, fila
from core.util import EMAIL_RE, ahora, cuerpo_json

bp = Blueprint("registro", __name__, url_prefix="/api/registro")


def usuario_por_correo(correo):
    return fila("SELECT * FROM usuarios WHERE email = ?", (correo.strip().lower(),))


def usuario_por_id(uid):
    return fila("SELECT id, nombre, apellidos, email, rol FROM usuarios WHERE id = ?", (uid,))


@bp.post("")
def registrar_usuario():
    # Misma validación y mismas respuestas que el servicio original.
    datos = cuerpo_json()
    nombre, email, password = datos.get("nombre"), datos.get("email"), datos.get("password")

    # 1. Validación básica
    if not nombre or not email or not password:
        return jsonify(exito=False, mensaje="Faltan campos obligatorios (nombre, email, password)."), 400
    if not all(isinstance(x, str) for x in (nombre, email, password)):
        return jsonify(exito=False, mensaje="nombre, email y password deben ser texto."), 400
    if not EMAIL_RE.match(email.strip()):
        return jsonify(exito=False, mensaje="El correo electrónico no es válido."), 400
    if len(password) < 8:
        return jsonify(exito=False, mensaje="La contraseña debe tener al menos 8 caracteres."), 400

    # 2. Verificar si el usuario ya existe
    email = email.strip().lower()
    if usuario_por_correo(email):
        return jsonify(exito=False, mensaje="El correo electrónico ya está registrado."), 409

    # 3-5. Cifrar la contraseña y guardar
    fecha = ahora()
    uid = ejecutar(
        "INSERT INTO usuarios(nombre, apellidos, email, password_hash, rol, fecha_registro) VALUES (?,?,?,?,?,?)",
        (nombre.strip(), str(datos.get("apellidos", "")).strip(), email,
         seguridad.hashear_contrasena(password), "cliente", fecha),
    )

    # 6. Respuesta (sin devolver la contraseña)
    return jsonify(
        exito=True,
        mensaje="Usuario registrado correctamente.",
        datos={"id": uid, "nombre": nombre.strip(), "email": email, "fechaRegistro": fecha},
    ), 201
