"""Servicio 16 · Lista de Empaque (nuevo): documento con lo que debe ir en la caja."""
from flask import Blueprint, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, entero, requiere_admin
from servicios import pedidos

bp = Blueprint("lista_empaque", __name__, url_prefix="/api/lista-empaque")


def armar(pedido_id):
    cab = fila("SELECT folio, fecha FROM listas_empaque WHERE pedido_id = ?", (pedido_id,))
    if not cab:
        return None
    p = pedidos.obtener(pedido_id)
    direccion = fila(
        """SELECT calle, numero, colonia, ciudad, estado, codigo_postal AS codigoPostal, referencia
           FROM direcciones WHERE id = ?""", (p["direccion_id"],)) if p["direccion_id"] else None
    items = filas(
        """SELECT i.sku, i.nombre, SUM(i.cantidad) AS cantidad, COALESCE(pr.ubicacion, '') AS ubicacion
           FROM pedido_items i LEFT JOIN productos pr ON pr.codigo = i.sku
           WHERE i.pedido_id = ? GROUP BY i.sku ORDER BY i.sku""", (pedido_id,))
    return {"folio": cab["folio"], "fecha": cab["fecha"], "pedidoId": pedido_id, "cliente": p["cliente_nombre"],
            "destino": direccion, "articulos": items, "totalPiezas": sum(i["cantidad"] for i in items)}


@bp.post("")
@requiere_admin
def generar():
    pedido_id = entero(cuerpo_json().get("pedidoId"), 1, "pedidoId")
    with conexion(inmediata=True) as c:
        p = c.execute("SELECT estado FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        if not p:
            raise ApiError(404, "Pedido no encontrado")
        if p["estado"] != "PICKING_COMPLETO":
            raise ApiError(409, "La lista de empaque se genera cuando el picking está completo.")
        if c.execute("SELECT 1 FROM listas_empaque WHERE pedido_id = ?", (pedido_id,)).fetchone():
            raise ApiError(409, "Este pedido ya tiene lista de empaque.")
        folio = "LE-{:05d}".format(c.execute("SELECT COALESCE(MAX(id), 0) FROM listas_empaque").fetchone()[0] + 1)
        c.execute("INSERT INTO listas_empaque(folio, pedido_id, fecha) VALUES (?,?,?)", (folio, pedido_id, ahora()))
    return jsonify(armar(pedido_id)), 201


@bp.get("/<int:pedido_id>")
@requiere_admin
def consultar(pedido_id):
    lista = armar(pedido_id)
    if not lista:
        raise ApiError(404, "Este pedido no tiene lista de empaque.")
    return jsonify(lista)
