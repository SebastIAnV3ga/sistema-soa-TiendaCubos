"""Servicio 15 · Gestión de Inventarios (original: Node + SQLite, Gesti-n-Inventario).

Mismas rutas y formas de respuesta (`id`, `name`, `stock`, `min`, `updated`).
El `id` de inventario es el código (SKU) del maestro de productos.
"""
import csv
import io
import json

from flask import Blueprint, Response, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, requiere_admin
from servicios import notificaciones

bp = Blueprint("inventarios", __name__, url_prefix="/api/inventarios")


def registrar_movimiento(c, producto, tipo, cantidad, referencia=""):
    """Cambia el stock dentro de la transacción `c` y deja el movimiento.
    Lo usan también Pedidos (venta) e Inspección de Devoluciones (devolucion)."""
    if tipo == "venta" and cantidad > producto["stock"]:
        raise ApiError(409, f"Venta rechazada: solo hay {producto['stock']} unidades disponibles.")
    stock = producto["stock"] + (-cantidad if tipo == "venta" else cantidad)
    fecha = ahora()
    c.execute("UPDATE productos SET stock = ?, actualizado = ? WHERE id = ?", (stock, fecha, producto["id"]))
    if tipo != "venta" and producto["stock"] == 0:
        avisar_reabasto(c, producto)
    mid = c.execute(
        """INSERT INTO movimientos(producto_id, producto_nombre, tipo, cantidad, stock_despues, referencia, fecha)
           VALUES (?,?,?,?,?,?,?)""",
        (producto["id"], producto["nombre"], tipo, cantidad, stock, referencia, fecha),
    ).lastrowid
    return {"id": mid, "product": producto["nombre"], "type": tipo, "qty": cantidad, "result": stock,
            "date": fecha, "productId": producto["codigo"], "previousStock": producto["stock"]}


def avisar_reabasto(c, producto):
    """Producto que vuelve a tener existencias: avisa por correo a quien lo pidió."""
    pendientes = c.execute("SELECT id, email FROM avisos_stock WHERE producto_id = ? AND notificado = 0",
                           (producto["id"],)).fetchall()
    for a in pendientes:
        notificaciones.notificar({"email": a["email"]}, "stock.disponible", producto["codigo"],
                                 f"{producto['nombre']} ya está disponible",
                                 f"Volvió a haber existencias de {producto['nombre']} en GESE CUBES.",
                                 ("EMAIL",), "success", c=c)
        c.execute("UPDATE avisos_stock SET notificado = 1 WHERE id = ?", (a["id"],))


@bp.get("/productos")
def productos():
    return jsonify(filas(
        """SELECT p.codigo AS id, p.nombre AS name, p.stock, p.stock_minimo AS min, p.actualizado AS updated,
                  p.precio AS price, p.marca, p.activo, c.nombre AS categoria, p.descripcion,
                  (SELECT group_concat(ruta, char(10)) FROM
                     (SELECT ruta FROM fotos_producto WHERE producto_id = p.id ORDER BY orden, id)) AS fotos
           FROM productos p JOIN categorias c ON c.id = p.categoria_id ORDER BY p.codigo"""))


@bp.get("/movimientos")
@requiere_admin
def movimientos():
    return jsonify(filas(
        """SELECT id, producto_nombre AS product, tipo AS type, cantidad AS qty,
                  stock_despues AS result, fecha AS date, referencia
           FROM movimientos ORDER BY id DESC LIMIT 200"""))


@bp.post("/productos")
@requiere_admin
def crear_producto():
    d = cuerpo_json()
    id_, name, stock, minimo = d.get("id"), d.get("name"), d.get("stock"), d.get("min")
    id_ = id_.strip().upper() if isinstance(id_, str) else ""
    name = name.strip() if isinstance(name, str) else ""
    ok_int = lambda v: type(v) is int and v >= 0
    if not id_ or not name or not ok_int(stock) or not ok_int(minimo):
        raise ApiError(400, "Completa correctamente los datos del producto.")
    precio = d.get("price", 0)
    if isinstance(precio, bool) or not isinstance(precio, (int, float)) or precio < 0:
        raise ApiError(400, "Completa correctamente los datos del producto.")
    fecha = ahora()
    with conexion() as c:
        if c.execute("SELECT 1 FROM productos WHERE codigo = ?", (id_,)).fetchone():
            raise ApiError(409, "Ese ID de producto ya existe.")
        cat = _categoria(c, d.get("categoria") or "Sin categoría")
        # Sin precio de venta el producto queda inactivo (no aparece en el catálogo).
        c.execute(
            """INSERT INTO productos(codigo, categoria_id, unidad_id, nombre, marca, precio, activo, stock,
                 stock_minimo, fecha_registro, actualizado) VALUES (?,?,1,?,?,?,?,?,?,?,?)""",
            (id_, cat, name, str(d.get("marca") or "").strip()[:40], precio, 1 if precio > 0 else 0, stock, minimo,
             fecha, fecha),
        )
    return jsonify({"id": id_, "name": name, "stock": stock, "min": minimo, "updated": fecha}), 201


def _categoria(c, nombre):
    nombre = str(nombre).strip()[:40]
    r = c.execute("SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()
    return r[0] if r else c.execute("INSERT INTO categorias(nombre) VALUES (?)", (nombre,)).lastrowid


@bp.put("/productos/<id>")
@requiere_admin
def editar_producto(id):
    """Edita precio, fotos, existencias y datos de un modelo. El cambio de
    existencias pasa por registrar_movimiento (queda en el historial y avisa
    a quien pidió aviso de disponibilidad)."""
    d = cuerpo_json()
    with conexion() as c:
        p = c.execute("SELECT * FROM productos WHERE codigo = ?", (id,)).fetchone()
        if not p:
            raise ApiError(404, "Producto no encontrado.")
        p = dict(p)
        precio = d.get("price", p["precio"])
        if isinstance(precio, bool) or not isinstance(precio, (int, float)) or precio < 0:
            raise ApiError(400, "El precio no es válido.")
        nombre = str(d.get("name", p["nombre"])).strip()
        if not nombre:
            raise ApiError(400, "El nombre es obligatorio.")
        minimo = d.get("min", p["stock_minimo"])
        if type(minimo) is not int or minimo < 0:
            raise ApiError(400, "El mínimo no es válido.")
        variantes = d.get("variantes")
        if variantes is not None and not (isinstance(variantes, dict) and all(
                isinstance(v, list) and all(isinstance(x, str) for x in v) for v in variantes.values())):
            raise ApiError(400, "Las variantes no son válidas.")
        stock = d.get("stock", p["stock"])
        if type(stock) is not int or stock < 0:
            raise ApiError(400, "Las existencias no son válidas.")
        fotos = d.get("fotos")
        if isinstance(fotos, list):
            fotos = [r.strip() for r in fotos if isinstance(r, str) and r.strip()]
            if any(not r.startswith(("/img/", "https://")) for r in fotos):
                raise ApiError(400, "Las fotos deben ser una ruta /img/… o una URL https.")
        c.execute(
            """UPDATE productos SET nombre = ?, marca = ?, descripcion = ?, precio = ?, stock_minimo = ?,
                 categoria_id = ?, variantes = ?, activo = ?, actualizado = ? WHERE id = ?""",
            (nombre, str(d.get("marca", p["marca"])).strip()[:40], str(d.get("descripcion", p["descripcion"])).strip()[:500],
             precio, minimo, _categoria(c, d["categoria"]) if d.get("categoria") else p["categoria_id"],
             json.dumps(variantes, ensure_ascii=False) if variantes is not None else p["variantes"],
             1 if d.get("activo", bool(p["activo"])) and precio > 0 else 0, ahora(), p["id"]))
        if isinstance(fotos, list):
            c.execute("DELETE FROM fotos_producto WHERE producto_id = ?", (p["id"],))
            for orden, ruta in enumerate(fotos):
                c.execute("INSERT INTO fotos_producto(producto_id, ruta, texto_alternativo, orden) VALUES (?,?,?,?)",
                          (p["id"], ruta, nombre, orden))
        if stock != p["stock"]:
            registrar_movimiento(c, p, "compra" if stock > p["stock"] else "venta", abs(stock - p["stock"]), "Edición manual")
    return jsonify({"id": id, "ok": True})


ABIERTOS = "('PAGADO','EN_PICKING','PICKING_COMPLETO','EMPACADO')"


@bp.get("/ventas-hoy")
@requiere_admin
def ventas_hoy():
    r = fila(
        """SELECT COUNT(*) AS pedidos, COALESCE(SUM(total), 0) AS total FROM pedidos
           WHERE substr(fecha, 1, 10) = ? AND estado NOT IN ('CREADO', 'CANCELADO')""", (ahora()[:10],))
    r["pendientes"] = fila(f"SELECT COUNT(*) AS n FROM pedidos WHERE estado IN {ABIERTOS}")["n"]
    return jsonify(r)


@bp.get("/pendientes.csv")
@requiere_admin
def pendientes_csv():
    """Pedidos pagados que aún no salen del almacén, para imprimir o abrir en Excel."""
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["Pedido", "Fecha", "Cliente", "Correo", "Destino", "SKU", "Producto", "Variante", "Cantidad"])
    for p in filas(f"SELECT * FROM pedidos WHERE estado IN {ABIERTOS} ORDER BY id"):
        e = json.loads(p["envio_json"]) if p["envio_json"] else {}
        destino = f"{e.get('calle', '')} {e.get('numero', '')}, {e.get('colonia', '')} {e.get('ciudad', '')}, {e.get('estado', '')} {e.get('codigoPostal', '')}" if e else ""
        for i in filas("SELECT * FROM pedido_items WHERE pedido_id = ?", (p["id"],)):
            w.writerow([p["id"], p["fecha"][:10], p["cliente_nombre"], p["cliente_email"], destino,
                        i["sku"], i["nombre"], i["variante"], i["cantidad"]])
    return Response("\ufeff" + salida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=pendientes.csv"})


@bp.delete("/productos/<id>")
@requiere_admin
def eliminar_producto(id):
    with conexion() as c:
        if not c.execute("DELETE FROM productos WHERE codigo = ?", (id,)).rowcount:
            raise ApiError(404, "Producto no encontrado.")
    return Response(status=204)


@bp.post("/movimientos")
@requiere_admin
def crear_movimiento():
    d = cuerpo_json()
    tipo, cantidad = d.get("type"), d.get("quantity")
    if tipo not in ("compra", "venta") or type(cantidad) is not int or cantidad < 1:
        raise ApiError(400, "El tipo de operación o la cantidad no son válidos.")
    with conexion() as c:
        fila_ = c.execute("SELECT * FROM productos WHERE codigo = ?", (d.get("productId"),)).fetchone()
        if not fila_:
            raise ApiError(404, "Producto no encontrado.")
        mov = registrar_movimiento(c, dict(fila_), tipo, cantidad, "Movimiento manual")
    return jsonify(mov), 201


@bp.get("/resumen")
@requiere_admin
def resumen():
    return jsonify(fila(
        """SELECT COUNT(*) AS totalProducts, COALESCE(SUM(stock), 0) AS totalUnits,
                  COALESCE(SUM(CASE WHEN stock <= stock_minimo THEN 1 ELSE 0 END), 0) AS lowProducts
           FROM productos"""))
