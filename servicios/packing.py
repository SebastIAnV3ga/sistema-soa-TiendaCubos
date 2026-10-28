"""Servicio 18 · Packing (original: Node/Express, Servicio-packing).

Misma ruta `POST /api/packing` con la misma validación y respuesta
(`mensaje` + `packing`); ahora persiste el empaque y avanza el pedido.
"""
from flask import Blueprint, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, requiere_admin
from servicios import pedidos

bp = Blueprint("packing", __name__, url_prefix="/api/packing")

COLS = """pedido_id AS pedidoId, tipo_empaque AS tipoEmpaque, peso, observaciones, estado,
          listo_para_envio AS listoParaEnvio, fecha_empaque AS fechaEmpaque"""


def _salida(f):
    f["listoParaEnvio"] = bool(f["listoParaEnvio"])
    return f


@bp.get("/estado")
def estado():
    return jsonify({"mensaje": "Servicio de Packing funcionando"})


@bp.post("")
@requiere_admin
def empacar():
    d = cuerpo_json()
    pedido_id, tipo, peso, obs = d.get("pedidoId"), d.get("tipoEmpaque"), d.get("peso"), d.get("observaciones")
    if not pedido_id or not tipo or not peso:
        return jsonify({"error": "Faltan datos del empaque"}), 400
    if type(pedido_id) is not int or not isinstance(tipo, str) or isinstance(peso, bool) \
            or not isinstance(peso, (int, float)) or peso <= 0:
        return jsonify({"error": "pedidoId debe ser entero, tipoEmpaque texto y peso un número mayor a 0"}), 400
    with conexion(inmediata=True) as c:
        p = c.execute("SELECT estado FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        if not p:
            raise ApiError(404, "Pedido no encontrado")
        if p["estado"] != "PICKING_COMPLETO":
            raise ApiError(409, "El pedido debe tener el picking completo antes de empacarse.")
        if not c.execute("SELECT 1 FROM listas_empaque WHERE pedido_id = ?", (pedido_id,)).fetchone():
            raise ApiError(409, "Genera primero la lista de empaque del pedido.")
        c.execute(
            """INSERT INTO packing(pedido_id, tipo_empaque, peso, observaciones, fecha_empaque)
               VALUES (?,?,?,?,?)""", (pedido_id, tipo.strip(), peso, (obs or "").strip() if isinstance(obs, str) else "", ahora()))
        pedidos.cambiar_estado(c, pedido_id, "EMPACADO", f"Empacado en {tipo.strip()}")
    return jsonify({"mensaje": "Pedido empacado correctamente",
                    "packing": _salida(fila(f"SELECT {COLS} FROM packing WHERE pedido_id = ?", (pedido_id,)))}), 201


@bp.get("")
@requiere_admin
def listar():
    return jsonify([_salida(f) for f in filas(f"SELECT {COLS} FROM packing ORDER BY id DESC LIMIT 200")])


@bp.get("/<int:pedido_id>")
@requiere_admin
def consultar(pedido_id):
    f = fila(f"SELECT {COLS} FROM packing WHERE pedido_id = ?", (pedido_id,))
    if not f:
        raise ApiError(404, "Este pedido no tiene empaque registrado.")
    return jsonify(_salida(f))
