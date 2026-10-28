"""Servicio 11 · Gestión de Pedidos (original: Python, Stock-sistema "Verifica Stock").

Conserva la lógica original: verificar disponibilidad por SKU y confirmar el
pedido descontando el stock en una sola transacción bloqueante (409 con el
detalle de faltantes si no alcanza). Añade: pedidos desde el carrito, usuario,
direcciones, totales con IVA y el ciclo de estados que usan los demás servicios.
"""
from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, entero, requiere_admin, requiere_sesion, texto
from servicios import inventarios, notificaciones

bp = Blueprint("pedidos", __name__, url_prefix="/api/pedidos")

IVA = 0.16

# Ciclo de vida de un pedido y cómo lo ve el cliente (Seguimiento).
ETIQUETAS = {
    "CREADO": "Pedido recibido",
    "PAGADO": "En preparación",
    "EN_PICKING": "En preparación",
    "PICKING_COMPLETO": "En preparación",
    "EMPACADO": "Empacado",
    "ENVIADO": "En camino",
    "ENTREGADO": "Entregado",
    "CANCELADO": "Cancelado",
}
AVISOS = {  # estado -> (asunto, mensaje, tipo) que ve el cliente
    "PAGADO": ("Pago confirmado", "Recibimos tu pago del pedido #{id}. Ya lo estamos preparando.", "success"),
    "ENVIADO": ("Tu pedido va en camino", "El pedido #{id} salió de nuestro almacén.", "info"),
    "ENTREGADO": ("Pedido entregado", "El pedido #{id} fue entregado. ¡Gracias por tu compra!", "success"),
}


# ---------------------------------------------------------- funciones públicas
def cambiar_estado(c, pedido_id, estado, detalle=""):
    """Actualiza el estado dentro de la transacción `c`, deja el evento de
    seguimiento y avisa al cliente en los hitos importantes."""
    c.execute("UPDATE pedidos SET estado = ? WHERE id = ?", (estado, pedido_id))
    c.execute("INSERT INTO pedido_eventos(pedido_id, estado, detalle, fecha) VALUES (?,?,?,?)",
              (pedido_id, estado, detalle or ETIQUETAS.get(estado, estado), ahora()))
    aviso = AVISOS.get(estado)
    p = c.execute("SELECT usuario_id FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if aviso and p and p["usuario_id"]:
        asunto, mensaje, tipo = aviso
        notificaciones.notificar({"id": p["usuario_id"]}, f"pedido.{estado.lower()}", pedido_id, asunto,
                                 mensaje.format(id=pedido_id), ("APP",), tipo, c=c)


def obtener(pedido_id):
    """Pedido con sus artículos, o None."""
    p = fila("SELECT * FROM pedidos WHERE id = ?", (pedido_id,))
    if not p:
        return None
    p["items"] = filas(
        "SELECT sku, nombre, cantidad, precio_unitario AS precioUnitario, variante FROM pedido_items WHERE pedido_id = ?",
        (pedido_id,))
    p["etiqueta"] = ETIQUETAS.get(p["estado"], p["estado"])
    return p


# --------------------------------------------------------- lógica de stock ----
def leer_items(body):
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise ApiError(400, "El pedido está vacío")
    cantidades = {}
    for item in items:
        if not isinstance(item, dict):
            raise ApiError(400, "Formato de pedido inválido")
        sku = texto(item.get("sku"), "sku")
        cantidades[sku] = cantidades.get(sku, 0) + entero(item.get("qty"), 1, "qty")
    return cantidades


def verificar(c, cantidades):
    lineas = []
    for sku, qty in cantidades.items():
        p = c.execute("SELECT nombre, stock, precio FROM productos WHERE codigo = ?", (sku,)).fetchone()
        if not p:
            raise ApiError(404, f"No existe el producto {sku}")
        lineas.append({"sku": sku, "nombre": p["nombre"], "pedido": qty, "disponible": p["stock"],
                       "faltante": max(0, qty - p["stock"]), "precio": p["precio"]})
    return {"ok": all(l["faltante"] == 0 for l in lineas), "lineas": lineas}


def _crear(c, cantidades, usuario, direccion_id=None, costo_envio=0, destino="", variantes=None):
    """Verifica, crea el pedido y descuenta el stock. `c` debe ser una
    transacción inmediata (conexion(inmediata=True)). `usuario["id"]` puede ser
    None (compra como invitado); `destino` es el JSON de envío de ese invitado."""
    resultado = verificar(c, cantidades)
    if not resultado["ok"]:
        raise ApiError(409, "No hay stock suficiente para confirmar el pedido", **resultado)
    subtotal = round(sum(l["pedido"] * l["precio"] for l in resultado["lineas"]), 2)
    impuestos = round(subtotal * IVA, 2)
    perfil = c.execute("SELECT telefono FROM perfiles WHERE usuario_id = ?", (usuario["id"],)).fetchone()
    nombre = f"{usuario['nombre']} {usuario.get('apellidos', '')}".strip()
    telefono = perfil["telefono"] if perfil else usuario.get("telefono", "")
    total = round(subtotal + impuestos + costo_envio, 2)
    fecha = ahora()
    pid = c.execute(
        """INSERT INTO pedidos(usuario_id, cliente_nombre, cliente_email, cliente_telefono, fecha, estado,
             subtotal, impuestos, total, direccion_id, costo_envio, envio_json)
           VALUES (?,?,?,?,?,'CREADO',?,?,?,?,?,?)""",
        (usuario["id"], nombre, usuario["email"], telefono, fecha,
         subtotal, impuestos, total, direccion_id, costo_envio, destino)).lastrowid
    for l in resultado["lineas"]:
        producto = c.execute("SELECT * FROM productos WHERE codigo = ?", (l["sku"],)).fetchone()
        inventarios.registrar_movimiento(c, dict(producto), "venta", l["pedido"], f"Pedido #{pid}")
        c.execute("INSERT INTO pedido_items(pedido_id, sku, nombre, cantidad, precio_unitario, variante) VALUES (?,?,?,?,?,?)",
                  (pid, l["sku"], l["nombre"], l["pedido"], l["precio"], (variantes or {}).get(l["sku"], "")))
    c.execute("INSERT INTO pedido_eventos(pedido_id, estado, detalle, fecha) VALUES (?, 'CREADO', 'Pedido recibido', ?)",
              (pid, fecha))
    notificaciones.notificar(usuario, "pedido.creado", pid, "Pedido recibido",
                             f"Recibimos tu pedido #{pid} por ${total:,.2f}. Falta confirmar el pago.",
                             ("APP", "EMAIL"), "info", c=c)
    return pid


# ----------------------------------------------------------------------- API ----
@bp.post("/verificar")
def api_verificar():
    cantidades = leer_items(cuerpo_json())
    with conexion() as c:
        resultado = verificar(c, cantidades)
    for l in resultado["lineas"]:
        l.pop("precio", None)
    return jsonify(resultado)


@bp.post("")
@requiere_sesion
def api_confirmar():
    d = cuerpo_json()
    cantidades = leer_items(d)
    direccion_id = d.get("direccionId")
    with conexion(inmediata=True) as c:
        pid = _crear(c, cantidades, g.usuario, direccion_id if type(direccion_id) is int else None)
    return jsonify(obtener(pid)), 201


@bp.post("/desde-carrito")
@requiere_sesion
def desde_carrito():
    d = cuerpo_json()
    carrito_id = entero(d.get("carritoId"), 1, "carritoId")
    direccion_id = entero(d.get("direccionId"), 1, "direccionId")
    with conexion(inmediata=True) as c:
        cab = c.execute("SELECT * FROM carritos WHERE id = ?", (carrito_id,)).fetchone()
        if not cab or cab["cliente_id"] != g.usuario["id"]:
            raise ApiError(404, "Carrito no encontrado.")
        if cab["estado"] != "Activo":
            raise ApiError(409, "El carrito no está activo.")
        dire = c.execute("SELECT usuario_id FROM direcciones WHERE id = ?", (direccion_id,)).fetchone()
        if not dire or dire["usuario_id"] != g.usuario["id"]:
            raise ApiError(404, "La dirección de envío no existe.")
        filas_ = c.execute(
            """SELECT p.codigo, i.cantidad FROM carrito_items i JOIN productos p ON p.id = i.producto_id
               WHERE i.carrito_id = ?""", (carrito_id,)).fetchall()
        if not filas_:
            raise ApiError(409, "No se puede confirmar un carrito vacío.")
        pid = _crear(c, {f["codigo"]: f["cantidad"] for f in filas_}, g.usuario, direccion_id)
        c.execute("UPDATE carritos SET estado = 'Confirmado' WHERE id = ?", (carrito_id,))
    return jsonify(obtener(pid)), 201


@bp.get("")
@requiere_admin
def listar():
    ids = [r["id"] for r in filas("SELECT id FROM pedidos ORDER BY id DESC LIMIT 100")]
    return jsonify([obtener(i) for i in ids])


@bp.get("/<int:id>")
@requiere_sesion
def uno(id):
    p = obtener(id)
    if not p or (g.usuario["rol"] != "admin" and p["usuario_id"] != g.usuario["id"]):
        raise ApiError(404, "Pedido no encontrado")
    return jsonify(p)
