"""Servicio 17 · Picking (original: Python/FastAPI, servicio-picking).

Mismas rutas, validaciones y mensajes: lista de pedidos por recoger y
registro de recogidas por SKU. Los pedidos y sus ubicaciones salen ahora
de los pedidos pagados del sistema.
"""
import threading

from flask import Blueprint, jsonify

from core.db import conexion
from core.util import cuerpo_json, requiere_admin
from servicios import pedidos

bp = Blueprint("picking", __name__, url_prefix="/api/picking")
bloqueo_db = threading.Lock()
ELEGIBLES = ("PAGADO", "EN_PICKING", "PICKING_COMPLETO")


def _error(status, detalle):
    return jsonify({"detail": detalle}), status


def _asegurar_items(c, pedido_id):
    """Crea la lista de picking de un pedido pagado la primera vez que se consulta."""
    if c.execute("SELECT 1 FROM picking_items WHERE pedido_id = ? LIMIT 1", (pedido_id,)).fetchone():
        return
    c.execute(
        """INSERT INTO picking_items(pedido_id, sku, nombre, ubicacion, cantidad_solicitada)
           SELECT i.pedido_id, i.sku, i.nombre, COALESCE(p.ubicacion, ''), SUM(i.cantidad)
           FROM pedido_items i LEFT JOIN productos p ON p.codigo = i.sku
           WHERE i.pedido_id = ? GROUP BY i.sku""", (pedido_id,))


def _estado(productos):
    if all(p["cantidad_recogida"] == p["cantidad_solicitada"] for p in productos):
        return "COMPLETADO"
    return "PENDIENTE" if all(p["cantidad_recogida"] == 0 for p in productos) else "EN_PROCESO"


def _pedido(c, pedido_id):
    p = c.execute("SELECT id, estado FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if not p or p["estado"] not in ELEGIBLES:
        return None
    _asegurar_items(c, pedido_id)
    productos = [dict(r) for r in c.execute(
        "SELECT sku, nombre, ubicacion, cantidad_solicitada, cantidad_recogida FROM picking_items WHERE pedido_id = ? ORDER BY sku",
        (pedido_id,))]
    return {"id": pedido_id, "estado": _estado(productos), "productos": productos}


@bp.get("/pedidos")
@requiere_admin
def listar_pedidos():
    with conexion() as c:
        ids = [r["id"] for r in c.execute(
            f"SELECT id FROM pedidos WHERE estado IN ({','.join('?' * len(ELEGIBLES))}) ORDER BY id", ELEGIBLES)]
        return jsonify([_pedido(c, i) for i in ids])


@bp.get("/pedidos/<int:pedido_id>")
@requiere_admin
def consultar_pedido(pedido_id):
    with conexion() as c:
        pedido = _pedido(c, pedido_id)
    if pedido is None:
        return _error(404, "Pedido no encontrado")
    return jsonify(pedido)


@bp.post("/pedidos/<int:pedido_id>/recogidas")
@requiere_admin
def registrar_recogida(pedido_id):
    datos = cuerpo_json()
    sku, cantidad = datos.get("sku"), datos.get("cantidad")
    if not isinstance(sku, str) or not sku:
        return _error(422, "sku: Este campo es obligatorio")
    if type(cantidad) is not int or cantidad <= 0:
        return _error(422, "cantidad: Debe ser un entero mayor que 0")
    with bloqueo_db, conexion(inmediata=True) as c:
        pedido = _pedido(c, pedido_id)
        if pedido is None:
            return _error(404, "Pedido no encontrado")
        producto = next((p for p in pedido["productos"] if p["sku"] == sku), None)
        if producto is None:
            return _error(404, "El producto no pertenece al pedido")
        pendientes = producto["cantidad_solicitada"] - producto["cantidad_recogida"]
        if cantidad > pendientes:
            return _error(400, f"Solo quedan {pendientes} unidades por recoger")
        producto["cantidad_recogida"] += cantidad
        c.execute("UPDATE picking_items SET cantidad_recogida = ? WHERE pedido_id = ? AND sku = ?",
                  (producto["cantidad_recogida"], pedido_id, sku))
        estado = _estado(pedido["productos"])
        if estado == "COMPLETADO":
            pedidos.cambiar_estado(c, pedido_id, "PICKING_COMPLETO", "Picking completado")
        elif c.execute("SELECT estado FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()["estado"] == "PAGADO":
            pedidos.cambiar_estado(c, pedido_id, "EN_PICKING", "Picking iniciado")
        return jsonify({
            "mensaje": "Recogida registrada", "pedido_id": pedido_id, "sku": sku,
            "cantidad_recogida": producto["cantidad_recogida"],
            "cantidad_pendiente": producto["cantidad_solicitada"] - producto["cantidad_recogida"],
            "estado": estado})
