"""Servicio 9 · Métodos de Pago (nuevo): tarjetas guardadas por usuario.

Por seguridad NUNCA se guarda el número completo ni el CVV: solo la marca y
los últimos 4 dígitos. El cobro real lo hace el servicio de Procesamiento.
"""
import re
from datetime import date

from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, requiere_sesion, texto

bp = Blueprint("metodos_pago", __name__, url_prefix="/api/metodos-pago")

COLS = "id, marca, ultimos4, titular, vence_mes AS venceMes, vence_anio AS venceAnio, predeterminado"


def _luhn(numero):
    suma, alterna = 0, False
    for ch in reversed(numero):
        n = int(ch)
        if alterna:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        suma += n
        alterna = not alterna
    return suma % 10 == 0


def _marca(n):
    if n.startswith("4"):
        return "Visa"
    if re.match(r"^(5[1-5]|2[2-7])", n):
        return "Mastercard"
    if re.match(r"^3[47]", n):
        return "American Express"
    return "Tarjeta"


def metodo_de_usuario(uid, metodo_id=None):
    if metodo_id is not None:
        return fila(f"SELECT {COLS} FROM metodos_pago WHERE id = ? AND usuario_id = ?", (metodo_id, uid))
    return fila(f"SELECT {COLS} FROM metodos_pago WHERE usuario_id = ? ORDER BY predeterminado DESC, id LIMIT 1", (uid,))


@bp.get("")
@requiere_sesion
def listar():
    return jsonify(filas(f"SELECT {COLS} FROM metodos_pago WHERE usuario_id = ? ORDER BY id", (g.usuario["id"],)))


@bp.post("")
@requiere_sesion
def crear():
    d = cuerpo_json()
    numero = re.sub(r"[\s-]", "", str(d.get("numero", "")))
    if not re.fullmatch(r"\d{13,19}", numero) or not _luhn(numero):
        raise ApiError(400, "El número de tarjeta no es válido.")
    mes, anio = d.get("venceMes"), d.get("venceAnio")
    if type(mes) is not int or not 1 <= mes <= 12 or type(anio) is not int:
        raise ApiError(400, "La fecha de vencimiento no es válida.")
    anio = anio + 2000 if anio < 100 else anio
    hoy = date.today()
    if (anio, mes) < (hoy.year, hoy.month):
        raise ApiError(400, "La tarjeta está vencida.")
    titular = texto(d.get("titular"), "titular", 100)
    uid = g.usuario["id"]
    with conexion() as c:
        primero = not c.execute("SELECT 1 FROM metodos_pago WHERE usuario_id = ?", (uid,)).fetchone()
        mid = c.execute(
            """INSERT INTO metodos_pago(usuario_id, marca, ultimos4, titular, vence_mes, vence_anio,
                 predeterminado, creado) VALUES (?,?,?,?,?,?,0,?)""",
            (uid, _marca(numero), numero[-4:], titular, mes, anio, ahora())).lastrowid
        if d.get("predeterminado") or primero:
            c.execute("UPDATE metodos_pago SET predeterminado = (id = ?) WHERE usuario_id = ?", (mid, uid))
    return jsonify(fila(f"SELECT {COLS} FROM metodos_pago WHERE id = ?", (mid,))), 201


@bp.put("/<int:id>/predeterminado")
@requiere_sesion
def predeterminar(id):
    uid = g.usuario["id"]
    with conexion() as c:
        if not c.execute("SELECT 1 FROM metodos_pago WHERE id = ? AND usuario_id = ?", (id, uid)).fetchone():
            raise ApiError(404, "Método de pago no encontrado.")
        c.execute("UPDATE metodos_pago SET predeterminado = (id = ?) WHERE usuario_id = ?", (id, uid))
    return jsonify(predeterminado=id)


@bp.delete("/<int:id>")
@requiere_sesion
def eliminar(id):
    with conexion() as c:
        if not c.execute("DELETE FROM metodos_pago WHERE id = ? AND usuario_id = ?", (id, g.usuario["id"])).rowcount:
            raise ApiError(404, "Método de pago no encontrado.")
    return jsonify(eliminado=id)
