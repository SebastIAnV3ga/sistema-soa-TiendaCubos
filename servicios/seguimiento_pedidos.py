"""Servicio 13 · Seguimiento de Pedidos (original: Python/FastAPI, seguimiento_pedidos).

`GET /pedidos/{id}` → `{id, cliente, estado}` (estado legible: "En preparación",
"En camino", "Entregado"…). Ahora lee los pedidos reales y añade el historial.
"""
from flask import Blueprint, g, jsonify

from core.db import fila, filas
from core.util import requiere_sesion
from servicios import pedidos

bp = Blueprint("seguimiento_pedidos", __name__, url_prefix="/api/seguimiento-pedidos")


@bp.get("")
def inicio():
    return jsonify({"mensaje": "Microservicio de seguimiento de pedidos funcionando"})


@bp.get("/pedidos/<int:pedido_id>")
@requiere_sesion
def consultar_pedido(pedido_id):
    p = fila("SELECT id, usuario_id, cliente_nombre, estado FROM pedidos WHERE id = ?", (pedido_id,))
    if not p or (g.usuario["rol"] != "admin" and p["usuario_id"] != g.usuario["id"]):
        return jsonify({"detail": "Pedido no encontrado"}), 404
    return jsonify({
        "id": p["id"],
        "cliente": p["cliente_nombre"],
        "estado": pedidos.ETIQUETAS.get(p["estado"], p["estado"]),
        "estadoCodigo": p["estado"],
        "historial": filas("SELECT estado, detalle, fecha FROM pedido_eventos WHERE pedido_id = ? ORDER BY id", (pedido_id,)),
        "envio": fila("SELECT paqueteria, guia, estado, fecha_envio AS fechaEnvio, fecha_entrega AS fechaEntrega FROM envios WHERE pedido_id = ?", (pedido_id,)),
    })
