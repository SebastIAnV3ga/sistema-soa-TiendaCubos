"""Servicio 6 · Carrito de Compras (original: C# ASP.NET, CarritoService).

Misma lógica de negocio, mismas rutas y códigos de respuesta
(404 / 400 / 409 / 204). Una mejora de seguridad: el nombre y el precio de
cada artículo se toman del catálogo, no de lo que envíe el cliente.
"""
from flask import Blueprint, Response, g, jsonify, request

from core.db import conexion, fila, filas
from core.util import ApiError, cuerpo_json, usuario_de_sesion

bp = Blueprint("carrito", __name__, url_prefix="/api/carritos")

IVA = 0.16


def _carrito_dict(c, carrito_id):
    cab = c.execute("SELECT id, cliente_id, estado FROM carritos WHERE id = ?", (carrito_id,)).fetchone()
    if not cab:
        return None
    items = []
    for r in c.execute(
        "SELECT producto_id, nombre_producto, precio_unitario, cantidad FROM carrito_items WHERE carrito_id = ? ORDER BY rowid",
        (carrito_id,),
    ):
        items.append({"productoId": r["producto_id"], "nombreProducto": r["nombre_producto"],
                      "precioUnitario": r["precio_unitario"], "cantidad": r["cantidad"],
                      "subtotal": round(r["precio_unitario"] * r["cantidad"], 2)})
    subtotal = round(sum(i["subtotal"] for i in items), 2)
    impuestos = round(subtotal * IVA, 2)
    return {"id": cab["id"], "clienteId": cab["cliente_id"], "estado": cab["estado"], "items": items,
            "subtotal": subtotal, "impuestos": impuestos, "total": round(subtotal + impuestos, 2)}


def obtener_carrito(carrito_id):
    with conexion() as c:
        return _carrito_dict(c, carrito_id)


def _mensaje(status, texto):
    return jsonify(mensaje=texto), status


def _activo(c, carrito_id):
    cab = c.execute("SELECT estado FROM carritos WHERE id = ?", (carrito_id,)).fetchone()
    if not cab:
        raise ApiError(404, "El carrito no existe.")
    if cab["estado"] != "Activo":
        raise ApiError(409, "El carrito no está activo.")


@bp.before_request
def _proteger():
    """Solo el dueño (o un administrador) puede ver y modificar un carrito."""
    usuario = usuario_de_sesion()
    if usuario is None:
        raise ApiError(401, "No has iniciado sesión.")
    g.usuario = usuario
    id_ = (request.view_args or {}).get("id")
    if id_ is not None and usuario["rol"] != "admin":
        cab = fila("SELECT cliente_id FROM carritos WHERE id = ?", (id_,))
        if cab and cab["cliente_id"] != usuario["id"]:
            raise ApiError(404, "Carrito no encontrado.")


@bp.errorhandler(ApiError)
def _errores(e):
    return _mensaje(e.status, str(e))  # este servicio responde {mensaje} como el original


# POST /api/carritos?clienteId=1
@bp.post("")
def crear_carrito():
    try:
        cliente_id = int(request.args.get("clienteId", 0))
    except ValueError:
        return _mensaje(400, "clienteId inválido.")
    if g.usuario["rol"] != "admin" and cliente_id != g.usuario["id"]:
        return _mensaje(403, "Solo puedes crear carritos a tu nombre.")
    with conexion() as c:
        cid = c.execute("INSERT INTO carritos(cliente_id, estado) VALUES (?, 'Activo')", (cliente_id,)).lastrowid
        return jsonify(_carrito_dict(c, cid)), 201


# GET /api/carritos/1
@bp.get("/<int:id>")
def ver_carrito(id):
    carrito = obtener_carrito(id)
    if carrito is None:
        return _mensaje(404, "Carrito no encontrado.")
    return jsonify(carrito)


# POST /api/carritos/1/items
@bp.post("/<int:id>/items")
def agregar_producto(id):
    d = cuerpo_json()
    producto_id, cantidad = d.get("productoId"), d.get("cantidad")
    with conexion() as c:
        _activo(c, id)
        if type(cantidad) is not int or cantidad <= 0:
            raise ApiError(400, "La cantidad debe ser mayor que cero.")
        prod = c.execute(
            "SELECT id, nombre, precio, stock FROM productos WHERE id = ? AND activo = 1", (producto_id,)
        ).fetchone()
        if not prod:
            raise ApiError(404, "El producto no existe en el catálogo.")
        existente = c.execute(
            "SELECT cantidad FROM carrito_items WHERE carrito_id = ? AND producto_id = ?", (id, prod["id"])
        ).fetchone()
        nueva = cantidad + (existente["cantidad"] if existente else 0)
        if nueva > prod["stock"]:
            raise ApiError(409, f"Solo hay {prod['stock']} unidades disponibles de {prod['nombre']}.")
        if existente:
            c.execute("UPDATE carrito_items SET cantidad = ? WHERE carrito_id = ? AND producto_id = ?",
                      (nueva, id, prod["id"]))
        else:
            c.execute(
                "INSERT INTO carrito_items(carrito_id, producto_id, nombre_producto, precio_unitario, cantidad) VALUES (?,?,?,?,?)",
                (id, prod["id"], prod["nombre"], prod["precio"], cantidad))
        return jsonify(_carrito_dict(c, id))


# PUT /api/carritos/1/items/10   (cuerpo: un entero, o {"cantidad": n})
@bp.put("/<int:id>/items/<int:producto_id>")
def actualizar_cantidad(id, producto_id):
    cuerpo = request.get_json(silent=True)
    cantidad = cuerpo.get("cantidad") if isinstance(cuerpo, dict) else cuerpo
    with conexion() as c:
        if not c.execute("SELECT 1 FROM carritos WHERE id = ?", (id,)).fetchone():
            return Response(status=404)
        _activo(c, id)
        if type(cantidad) is not int or cantidad <= 0:
            raise ApiError(400, "La cantidad debe ser mayor que cero.")
        if not c.execute("SELECT 1 FROM carrito_items WHERE carrito_id = ? AND producto_id = ?", (id, producto_id)).fetchone():
            return Response(status=404)
        stock = c.execute("SELECT stock, nombre FROM productos WHERE id = ?", (producto_id,)).fetchone()
        if stock and cantidad > stock["stock"]:
            raise ApiError(409, f"Solo hay {stock['stock']} unidades disponibles de {stock['nombre']}.")
        c.execute("UPDATE carrito_items SET cantidad = ? WHERE carrito_id = ? AND producto_id = ?",
                  (cantidad, id, producto_id))
        return jsonify(_carrito_dict(c, id))


# DELETE /api/carritos/1/items/10
@bp.delete("/<int:id>/items/<int:producto_id>")
def eliminar_producto(id, producto_id):
    with conexion() as c:
        if not c.execute("DELETE FROM carrito_items WHERE carrito_id = ? AND producto_id = ?", (id, producto_id)).rowcount:
            return Response(status=404)
    return Response(status=204)


# DELETE /api/carritos/1/items
@bp.delete("/<int:id>/items")
def vaciar_carrito(id):
    with conexion() as c:
        if not c.execute("SELECT 1 FROM carritos WHERE id = ?", (id,)).fetchone():
            return Response(status=404)
        c.execute("DELETE FROM carrito_items WHERE carrito_id = ?", (id,))
    return Response(status=204)


# POST /api/carritos/1/confirmar
@bp.post("/<int:id>/confirmar")
def confirmar_carrito(id):
    with conexion() as c:
        carrito = _carrito_dict(c, id)
        if carrito is None:
            return Response(status=404)
        if not carrito["items"]:
            raise ApiError(409, "No se puede confirmar un carrito vacío.")
        c.execute("UPDATE carritos SET estado = 'Confirmado' WHERE id = ?", (id,))
        return jsonify(_carrito_dict(c, id))
