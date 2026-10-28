"""Servicio 5 · Detalle de Productos (original: Python/Flask + SQL Server)."""
from flask import Blueprint, jsonify

from core.db import fila

bp = Blueprint("detalle_productos", __name__, url_prefix="/api/detalle-productos")


@bp.get("/<int:id>")
def obtener_producto(id):
    if id == 0:
        return jsonify({"error": "Sin id"}), 400
    f = fila(
        """SELECT p.id, p.codigo, p.nombre, p.descripcion, p.stock, p.precio_compra, p.precio,
                  p.fecha_registro, p.activo,
                  c.id AS categoria_id, c.nombre AS categoria,
                  pr.id AS proveedor_id, pr.nombre AS proveedor,
                  u.id AS medida_id, u.nombre AS medida
           FROM productos p
           LEFT JOIN categorias c ON p.categoria_id = c.id
           LEFT JOIN proveedores pr ON p.proveedor_id = pr.id
           LEFT JOIN unidades_medida u ON p.unidad_id = u.id
           WHERE p.id = ?""",
        (id,),
    )
    if not f:
        return jsonify({"mensaje": "Producto no encontrado"}), 404
    producto = {
        "id": f["id"], "codigo": f["codigo"], "nombre": f["nombre"], "descripcion": f["descripcion"],
        "categoria_id": f["categoria_id"], "categoria": f["categoria"],
        "proveedor_id": f["proveedor_id"], "proveedor": f["proveedor"],
        "stock": f["stock"], "precio_compra": f["precio_compra"], "precio_venta": f["precio"],
        "medida_id": f["medida_id"], "medida": f["medida"],
        "fecha_registro": f["fecha_registro"], "estado": bool(f["activo"]),
    }
    return jsonify({"producto": producto}), 200
