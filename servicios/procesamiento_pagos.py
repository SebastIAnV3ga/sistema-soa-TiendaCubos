"""Servicio 10 · Procesamiento de Pagos (original: Python/Flask + Stripe).

Conserva las rutas y funciones del servicio original (usuarios, métodos de
pago, productos, pagos, intent y flujo de prueba). Funciona en dos modos:
  - "stripe":    si hay STRIPE_SECRET_KEY y el paquete `stripe` instalado.
  - "simulado":  sin llaves; responde con ids ficticios (útil para desarrollar).
Añade `POST /pagar`, que cobra un pedido del sistema con una tarjeta guardada.
"""
import os
import uuid

from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, entero, requiere_sesion
from servicios import metodos_pago, pedidos

try:  # el paquete es opcional
    import stripe
except ImportError:  # pragma: no cover
    stripe = None

bp = Blueprint("procesamiento_pagos", __name__, url_prefix="/api/procesamiento-pagos")

CLAVE = os.getenv("STRIPE_SECRET_KEY", "")
MODO = "stripe" if (stripe and CLAVE) else "simulado"
if MODO == "stripe":
    stripe.api_key = CLAVE

_ErrStripe = (getattr(stripe, "StripeError", None) or getattr(getattr(stripe, "error", None), "StripeError", Exception)) if stripe else Exception
_ErrTarjeta = (getattr(stripe, "CardError", None) or getattr(getattr(stripe, "error", None), "CardError", Exception)) if stripe else Exception


class PagoError(Exception):
    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


@bp.errorhandler(PagoError)
def _pago_error(e):
    return jsonify({"error": e.mensaje}), e.codigo


def _stripe(fn):
    try:
        return fn()
    except _ErrStripe as e:
        raise PagoError(getattr(e, "user_message", None) or str(e), 502)


def _sim_id(prefijo):
    return f"{prefijo}_sim_{uuid.uuid4().hex[:14]}"


# -------------------------------------------------- funciones del original ----
def crear_usuario(name, email):
    if not name or not email:
        raise PagoError("name y email son requeridos")
    if MODO == "simulado":
        return {"id": _sim_id("cus"), "name": name, "email": email}
    c = _stripe(lambda: stripe.Customer.create(name=name, email=email))
    return {"id": c.id, "name": c.name, "email": c.email}


def crear_metodo_pago(token="tok_visa"):
    if MODO == "simulado":
        return {"id": _sim_id("pm")}
    m = _stripe(lambda: stripe.PaymentMethod.create(type="card", card={"token": token}))
    return {"id": m.id}


def asociar_metodo_pago(client_id, payment_method_id):
    if not client_id or not payment_method_id:
        raise PagoError("clientId y paymentMethodId son requeridos")
    if MODO == "stripe":
        _stripe(lambda: stripe.PaymentMethod.attach(payment_method_id, customer=client_id))
    return {"clientId": client_id, "paymentMethodId": payment_method_id, "asociado": True}


def listar_productos():
    if MODO == "simulado":
        return [{"id": p["codigo"], "nombre": p["nombre"]} for p in filas("SELECT codigo, nombre FROM productos WHERE activo = 1 LIMIT 20")]
    r = _stripe(lambda: stripe.Product.list(active=True, limit=20))
    return [{"id": p["id"], "nombre": p["name"]} for p in r["data"]]


def obtener_producto():
    lista = listar_productos()
    if not lista:
        raise PagoError("No hay productos configurados en Stripe", 404)
    return lista[0]


def obtener_precio_producto(product_id):
    if not product_id:
        raise PagoError("product_id es requerido")
    if MODO == "simulado":
        p = fila("SELECT precio FROM productos WHERE codigo = ?", (product_id,))
        if not p:
            raise PagoError("El producto no tiene un precio configurado", 404)
        return {"priceId": _sim_id("price"), "amount": int(round(p["precio"] * 100)), "currency": "mxn"}
    r = _stripe(lambda: stripe.Price.list(product=product_id, limit=1))
    if not r["data"]:
        raise PagoError("El producto no tiene un precio configurado", 404)
    pr = r["data"][0]
    return {"priceId": pr["id"], "amount": pr["unit_amount"], "currency": pr["currency"]}


def crear_pago(client_id, payment_method_id, product_id, amount, currency):
    if not all([client_id, payment_method_id, product_id, amount, currency]):
        raise PagoError("clientId, paymentMethodId, productId, amount y currency son requeridos")
    if MODO == "simulado":
        return {"id": _sim_id("pi"), "estado": "succeeded", "monto": amount, "moneda": currency}
    try:
        pago = stripe.PaymentIntent.create(
            amount=amount, currency=currency, customer=client_id, payment_method=payment_method_id,
            payment_method_types=["card"], confirm=True, metadata={"product_id": product_id})
        return {"id": pago.id, "estado": pago.status, "monto": amount, "moneda": currency}
    except _ErrTarjeta as e:
        raise PagoError(getattr(e, "user_message", None) or "La tarjeta fue rechazada", 402)
    except _ErrStripe as e:
        raise PagoError(getattr(e, "user_message", None) or str(e), 502)


def crear_intento_pago(client_id, amount, currency, product_id):
    """PaymentIntent sin confirmar; el navegador (Stripe.js) lo confirma con el client_secret."""
    if not all([client_id, amount, currency]):
        raise PagoError("clientId, amount y currency son requeridos")
    if MODO == "simulado":
        return {"clientSecret": _sim_id("secret"), "id": _sim_id("pi")}
    i = _stripe(lambda: stripe.PaymentIntent.create(
        amount=amount, currency=currency, customer=client_id, automatic_payment_methods={"enabled": True},
        metadata={"product_id": product_id} if product_id else {}))
    return {"clientSecret": i.client_secret, "id": i.id}


def flujo_completo_de_prueba(name, email):
    cliente = crear_usuario(name, email)
    metodo = crear_metodo_pago()
    asociar_metodo_pago(cliente["id"], metodo["id"])
    producto = obtener_producto()
    precio = obtener_precio_producto(producto["id"])
    pago = crear_pago(cliente["id"], metodo["id"], producto["id"], precio["amount"], precio["currency"])
    return {"cliente": cliente, "metodo": metodo, "producto": producto, "precio": precio, "pago": pago}


# --------------------------------------------------------- rutas del original ----
@bp.get("/config")
def config():
    return jsonify({"publishableKey": os.getenv("STRIPE_PUBLISHABLE_KEY", ""), "modo": MODO})


@bp.post("/pagos/intent")
@requiere_sesion
def r_intent():
    d = cuerpo_json()
    return jsonify(crear_intento_pago(d.get("clientId"), d.get("amount"), d.get("currency"), d.get("productId"))), 201


@bp.post("/usuarios")
@requiere_sesion
def r_usuario():
    d = cuerpo_json()
    return jsonify(crear_usuario(d.get("name"), d.get("email"))), 201


@bp.post("/metodos-pago")
@requiere_sesion
def r_metodo():
    return jsonify(crear_metodo_pago(cuerpo_json().get("token", "tok_visa"))), 201


@bp.post("/metodos-pago/asociar")
@requiere_sesion
def r_asociar():
    d = cuerpo_json()
    return jsonify(asociar_metodo_pago(d.get("clientId"), d.get("paymentMethodId"))), 200


@bp.get("/productos/primero")
def r_primero():
    return jsonify(obtener_producto())


@bp.get("/productos")
def r_productos():
    return jsonify(listar_productos())


@bp.get("/productos/<product_id>/precio")
def r_precio(product_id):
    return jsonify(obtener_precio_producto(product_id))


@bp.post("/pagos")
@requiere_sesion
def r_pago():
    d = cuerpo_json()
    return jsonify(crear_pago(d.get("clientId"), d.get("paymentMethodId"), d.get("productId"),
                              d.get("amount"), d.get("currency"))), 201


@bp.post("/pagos/prueba-completa")
@requiere_sesion
def r_prueba():
    d = cuerpo_json()
    return jsonify(flujo_completo_de_prueba(d.get("name"), d.get("email"))), 201


# ------------------------------------------------------ cobro de un pedido ----
@bp.post("/pagar")
@requiere_sesion
def pagar():
    """Cobra un pedido con una tarjeta guardada del usuario.

    En modo simulado toda tarjeta se aprueba salvo las terminadas en 0002
    (equivale a la tarjeta de rechazo de las pruebas de Stripe)."""
    d = cuerpo_json()
    pedido_id = entero(d.get("pedidoId"), 1, "pedidoId")
    metodo_id = entero(d.get("metodoPagoId"), 1, "metodoPagoId")
    with conexion(inmediata=True) as c:
        p = c.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        if not p or p["usuario_id"] != g.usuario["id"]:
            raise ApiError(404, "Pedido no encontrado")
        if p["estado"] != "CREADO":
            raise ApiError(409, f"El pedido #{pedido_id} ya no está pendiente de pago.")
        metodo = metodos_pago.metodo_de_usuario(g.usuario["id"], metodo_id)
        if not metodo:
            raise ApiError(404, "Método de pago no encontrado.")
        if metodo["ultimos4"] == "0002":
            c.execute("INSERT INTO pagos(pedido_id, monto, estado, referencia, metodo, fecha) VALUES (?,?,?,?,?,?)",
                      (pedido_id, p["total"], "declined", "", f"{metodo['marca']} ****{metodo['ultimos4']}", ahora()))
            c.commit()
            raise ApiError(402, "La tarjeta fue rechazada por el banco emisor.")
        referencia = _sim_id("pi")
        pago_id = c.execute(
            "INSERT INTO pagos(pedido_id, monto, estado, referencia, metodo, fecha) VALUES (?,?,?,?,?,?)",
            (pedido_id, p["total"], "succeeded", referencia, f"{metodo['marca']} ****{metodo['ultimos4']}", ahora())).lastrowid
        c.execute("UPDATE pedidos SET metodo_pago = 'TARJETA' WHERE id = ?", (pedido_id,))
        pedidos.cambiar_estado(c, pedido_id, "PAGADO", f"Pago aprobado ({metodo['marca']} ****{metodo['ultimos4']})")
    return jsonify({"id": pago_id, "pedidoId": pedido_id, "estado": "succeeded", "monto": p["total"],
                    "moneda": "mxn", "referencia": referencia, "modo": MODO}), 201


@bp.get("/pagos")
@requiere_sesion
def listar_pagos():
    if g.usuario["rol"] == "admin":
        return jsonify(filas("SELECT * FROM pagos ORDER BY id DESC LIMIT 200"))
    return jsonify(filas(
        "SELECT pg.* FROM pagos pg JOIN pedidos p ON p.id = pg.pedido_id WHERE p.usuario_id = ? ORDER BY pg.id DESC",
        (g.usuario["id"],)))
