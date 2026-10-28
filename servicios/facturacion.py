"""Servicio 14 · Facturación (nuevo): factura de un pedido pagado con los datos fiscales del cliente."""
from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, entero, requiere_sesion
from servicios import datos_facturacion, notificaciones

bp = Blueprint("facturacion", __name__, url_prefix="/api/facturacion")

COLS = """folio, pedido_id AS pedidoId, rfc, razon_social AS razonSocial, regimen_fiscal AS regimenFiscal,
          codigo_postal AS codigoPostal, uso_cfdi AS usoCfdi, subtotal, iva, total, estado, fecha"""


def _puede(pedido):
    return pedido and (g.usuario["rol"] == "admin" or pedido["usuario_id"] == g.usuario["id"])


@bp.post("")
@requiere_sesion
def emitir():
    pedido_id = entero(cuerpo_json().get("pedidoId"), 1, "pedidoId")
    with conexion(inmediata=True) as c:
        p = c.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        if not _puede(p):
            raise ApiError(404, "Pedido no encontrado")
        if p["estado"] in ("CREADO", "CANCELADO"):
            raise ApiError(409, "Solo se pueden facturar pedidos pagados.")
        if c.execute("SELECT 1 FROM facturas WHERE pedido_id = ?", (pedido_id,)).fetchone():
            raise ApiError(409, "Este pedido ya tiene factura.")
        fiscales = datos_facturacion.predeterminados_de(p["usuario_id"]) if p["usuario_id"] else None
        if not fiscales:
            raise ApiError(409, "Registra tus datos de facturación antes de emitir la factura.")
        folio = "F-{:05d}".format((c.execute("SELECT COALESCE(MAX(id), 0) FROM facturas").fetchone()[0]) + 1)
        c.execute(
            """INSERT INTO facturas(folio, pedido_id, usuario_id, rfc, razon_social, regimen_fiscal, codigo_postal,
                 uso_cfdi, subtotal, iva, total, fecha) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (folio, pedido_id, p["usuario_id"], fiscales["rfc"], fiscales["razon_social"], fiscales["regimen_fiscal"],
             fiscales["codigo_postal"], fiscales["uso_cfdi"], p["subtotal"], p["impuestos"], p["total"], ahora()))
        notificaciones.notificar({"id": p["usuario_id"]}, "factura.emitida", folio, "Factura emitida",
                                 f"Tu factura {folio} del pedido #{pedido_id} ya está disponible.",
                                 ("APP", "EMAIL"), "success", c=c)
    return jsonify(fila(f"SELECT {COLS} FROM facturas WHERE pedido_id = ?", (pedido_id,))), 201


@bp.get("/pedido/<int:pedido_id>")
@requiere_sesion
def por_pedido(pedido_id):
    p = fila("SELECT usuario_id FROM pedidos WHERE id = ?", (pedido_id,))
    f = fila(f"SELECT {COLS} FROM facturas WHERE pedido_id = ?", (pedido_id,))
    if not _puede(p) or not f:
        raise ApiError(404, "Factura no encontrada")
    return jsonify(f)


@bp.get("")
@requiere_sesion
def listar():
    if g.usuario["rol"] == "admin":
        return jsonify(filas(f"SELECT {COLS} FROM facturas ORDER BY id DESC LIMIT 200"))
    return jsonify(filas(f"SELECT {COLS} FROM facturas WHERE usuario_id = ? ORDER BY id DESC", (g.usuario["id"],)))
