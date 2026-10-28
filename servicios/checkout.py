"""Servicio 24 · Checkout (nuevo, GESE CUBES).

Compra directa, con o sin cuenta (invitado): cotiza el envío por código postal,
crea el pedido descontando el stock (Pedidos) y cobra con Stripe, Mercado Pago
o genera la ficha de pago en OXXO. Las tres pasarelas funcionan en modo
sandbox simulado: no hay llaves reales (ver README).
"""
import json
import random
import re

from flask import Blueprint, g, jsonify, request

from core import seguridad
from core.db import conexion, fila
from core.util import EMAIL_RE, ApiError, ahora, cuerpo_json, entero, requiere_admin, texto, texto_opcional, usuario_de_sesion
from servicios import pedidos

bp = Blueprint("checkout", __name__, url_prefix="/api/checkout")

ENVIO_GRATIS_DESDE = 800  # MXN, antes de IVA
METODOS = ("stripe", "mercadopago", "oxxo")
ETIQUETA_PAGO = {"stripe": "Tarjeta (Stripe)", "mercadopago": "Mercado Pago", "oxxo": "OXXO"}


def cotizar(cp, subtotal):
    """Costo de envío por zona del C.P.

    shortcut: tarifas fijas por prefijo de C.P. (origen Los Mochis), no una API
    de paquetería; sustituir por la cotización real de la paquetería al contratar."""
    if not re.fullmatch(r"\d{5}", cp or ""):
        raise ApiError(400, "El código postal debe tener 5 dígitos.")
    p2 = int(cp[:2])
    zona, costo, dias = (("Sinaloa", 79, "1-2") if 80 <= p2 <= 82
                         else ("Noroeste", 119, "2-3") if p2 in (83, 84, 85, 21, 22, 23)
                         else ("Centro", 149, "3-4") if p2 < 20 or 50 <= p2 <= 59 or 70 <= p2 <= 79
                         else ("Resto del país", 169, "4-6"))
    gratis = subtotal > ENVIO_GRATIS_DESDE
    return {"cp": cp, "zona": zona, "dias": dias, "costo": 0 if gratis else costo, "gratis": gratis,
            "tarifa": costo, "faltaParaGratis": 0 if gratis else round(ENVIO_GRATIS_DESDE - subtotal + 0.01, 2)}


def _subtotal(c, cantidades):
    total = 0
    for sku, qty in cantidades.items():
        p = c.execute("SELECT precio FROM productos WHERE codigo = ? AND activo = 1", (sku,)).fetchone()
        if not p:
            raise ApiError(404, f"No existe el producto {sku}")
        total += p["precio"] * qty
    return round(total, 2)


@bp.get("/cotizar-envio")
def cotizar_envio():
    try:
        subtotal = float(request.args.get("subtotal", 0))
    except ValueError:
        raise ApiError(400, "El subtotal no es válido.")
    return jsonify(cotizar(request.args.get("cp", ""), subtotal))


def _variantes(c, items):
    """Valida las opciones elegidas contra las del producto y devuelve {sku: 'Base: Negro · Versión: Magnético'}.
    shortcut: si un mismo SKU se compra con dos variantes se guarda una línea con ambas etiquetas."""
    etiquetas = {}
    for it in items:
        sku = texto(it.get("sku"), "sku")
        p = c.execute("SELECT variantes FROM productos WHERE codigo = ?", (sku,)).fetchone()
        if not p:
            raise ApiError(404, f"No existe el producto {sku}")
        permitidas = json.loads(p["variantes"] or "{}")
        elegidas = it.get("variante") or {}
        if not isinstance(elegidas, dict) or any(permitidas.get(k) is None or v not in permitidas[k] for k, v in elegidas.items()):
            raise ApiError(400, f"La variante elegida de {sku} no existe.")
        if permitidas and set(elegidas) != set(permitidas):
            raise ApiError(400, f"Elige todas las opciones de {sku}.")
        etiqueta = " · ".join(f"{k}: {v}" for k, v in elegidas.items())
        previas = [e for e in etiquetas.get(sku, "").split(" | ") if e]
        if etiqueta and etiqueta not in previas:
            previas.append(etiqueta)
        etiquetas[sku] = " | ".join(previas)
    return etiquetas


def _validar_envio(d):
    if not isinstance(d, dict):
        raise ApiError(400, "Faltan los datos de envío.")
    e = {k: texto(d.get(k), k, 120) for k in ("nombre", "email", "calle", "ciudad", "estado")}
    if not EMAIL_RE.match(e["email"]):
        raise ApiError(400, "El correo electrónico no es válido.")
    e["email"] = e["email"].lower()
    e["codigoPostal"] = texto(d.get("codigoPostal"), "codigoPostal", 5)
    e["telefono"] = texto_opcional(d.get("telefono"), 20) or ""
    e["numero"] = texto_opcional(d.get("numero"), 20) or ""
    e["colonia"] = texto_opcional(d.get("colonia"), 80) or ""
    e["referencia"] = texto_opcional(d.get("referencia"), 200) or ""
    return e


def _cobrar_tarjeta(t):
    """Stripe en sandbox: valida la tarjeta de prueba; no se guarda ningún dato."""
    num = re.sub(r"\D", "", str((t or {}).get("numero", "")))
    if not 13 <= len(num) <= 19:
        raise ApiError(400, "El número de tarjeta no es válido.")
    if not re.fullmatch(r"\d{3,4}", str((t or {}).get("cvc", ""))):
        raise ApiError(400, "El código de seguridad no es válido.")
    if num.endswith("0002"):
        raise ApiError(402, "La tarjeta fue rechazada por el banco emisor.")
    return f"pi_sim_{random.randrange(10**13, 10**14)}", f"Visa ****{num[-4:]}" if num[0] == "4" else f"Tarjeta ****{num[-4:]}"


@bp.post("/pedido")
def crear_pedido():
    d = cuerpo_json()
    items = d.get("items")
    if not isinstance(items, list) or not items or not all(isinstance(i, dict) for i in items):
        raise ApiError(400, "Tu carrito está vacío.")
    cantidades = {}
    for i in items:
        sku = texto(i.get("sku"), "sku")
        cantidades[sku] = cantidades.get(sku, 0) + entero(i.get("qty"), 1, "qty")
    metodo = d.get("metodo")
    if metodo not in METODOS:
        raise ApiError(400, "Elige un método de pago: Stripe, Mercado Pago u OXXO.")
    envio = _validar_envio(d.get("envio"))
    cuenta = d.get("crearCuenta")
    sesion = usuario_de_sesion()

    # El rechazo de la tarjeta debe ocurrir antes de tocar el inventario.
    referencia, detalle_pago = None, ETIQUETA_PAGO[metodo]
    if metodo == "stripe":
        referencia, detalle_pago = _cobrar_tarjeta(d.get("tarjeta"))
    elif metodo == "mercadopago":
        referencia = f"mp_sim_{random.randrange(10**9, 10**10)}"
    else:
        referencia = "".join(random.choices("0123456789", k=14))

    with conexion(inmediata=True) as c:
        env = cotizar(envio["codigoPostal"], _subtotal(c, cantidades))
        etiquetas = _variantes(c, items)
        if sesion:
            usuario = dict(sesion, telefono=envio["telefono"])
        else:
            usuario = {"id": None, "nombre": envio["nombre"], "apellidos": "", "email": envio["email"],
                       "telefono": envio["telefono"]}
            if cuenta:
                pw = (cuenta or {}).get("password") if isinstance(cuenta, dict) else None
                if not isinstance(pw, str) or len(pw) < 8:
                    raise ApiError(400, "La contraseña debe tener al menos 8 caracteres.")
                if c.execute("SELECT 1 FROM usuarios WHERE email = ?", (envio["email"],)).fetchone():
                    raise ApiError(409, "Ese correo ya tiene cuenta. Inicia sesión para comprar.")
                uid = c.execute(
                    "INSERT INTO usuarios(nombre, apellidos, email, password_hash, rol, fecha_registro) VALUES (?,?,?,?,?,?)",
                    (envio["nombre"], "", envio["email"], seguridad.hashear_contrasena(pw), "cliente", ahora())).lastrowid
                usuario["id"] = uid
        direccion_id = None
        if usuario["id"]:  # guarda la dirección para próximas compras
            direccion_id = c.execute(
                """INSERT INTO direcciones(usuario_id, calle, numero, colonia, ciudad, estado, codigo_postal,
                     referencia, fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?)""",
                (usuario["id"], envio["calle"], envio["numero"], envio["colonia"], envio["ciudad"], envio["estado"],
                 envio["codigoPostal"], envio["referencia"], ahora())).lastrowid
        pid = pedidos._crear(c, cantidades, usuario, direccion_id, env["costo"],
                             json.dumps(envio, ensure_ascii=False), etiquetas)
        total = c.execute("SELECT total FROM pedidos WHERE id = ?", (pid,)).fetchone()["total"]
        c.execute("UPDATE pedidos SET metodo_pago = ? WHERE id = ?", (metodo.upper(), pid))
        estado_pago = "pending" if metodo == "oxxo" else "succeeded"
        c.execute("INSERT INTO pagos(pedido_id, monto, estado, referencia, metodo, fecha) VALUES (?,?,?,?,?,?)",
                  (pid, total, estado_pago, referencia, detalle_pago, ahora()))
        if metodo != "oxxo":
            pedidos.cambiar_estado(c, pid, "PAGADO", f"Pago aprobado ({detalle_pago})")
    resp = {"pedido": pedidos.obtener(pid), "metodo": metodo, "referencia": referencia,
            "cuentaCreada": bool(usuario["id"] and not sesion), "envio": env}
    if metodo == "oxxo":
        resp["oxxo"] = {"referencia": referencia, "monto": total, "vigencia": "72 horas"}
    return jsonify(resp), 201


@bp.get("/pedido/<int:id>")
def consultar(id):
    """Seguimiento de un pedido de invitado con su correo (?email=)."""
    p = pedidos.obtener(id)
    email = (request.args.get("email") or "").strip().lower()
    if not p or p["cliente_email"].lower() != email:
        raise ApiError(404, "Pedido no encontrado.")
    return jsonify(p)


@bp.post("/oxxo/<int:id>/confirmar")
@requiere_admin
def confirmar_oxxo(id):
    """Simula el aviso de OXXO Pay: marca la ficha como pagada."""
    with conexion(inmediata=True) as c:
        p = c.execute("SELECT estado FROM pedidos WHERE id = ?", (id,)).fetchone()
        pago = c.execute("SELECT id FROM pagos WHERE pedido_id = ? AND estado = 'pending'", (id,)).fetchone()
        if not p or not pago:
            raise ApiError(404, "No hay un pago OXXO pendiente para este pedido.")
        c.execute("UPDATE pagos SET estado = 'succeeded', fecha = ? WHERE id = ?", (ahora(), pago["id"]))
        pedidos.cambiar_estado(c, id, "PAGADO", "Pago recibido en OXXO")
    return jsonify({"ok": True})
