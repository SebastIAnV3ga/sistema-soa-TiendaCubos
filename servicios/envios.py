"""Servicio 19 · Gestión de Envíos (nuevo): guía, paquetería y estado de entrega."""
import secrets

from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, entero, requiere_admin, requiere_sesion
from servicios import pedidos

bp = Blueprint("envios", __name__, url_prefix="/api/envios")

PAQUETERIAS = ("Estafeta", "DHL", "FedEx", "Paquetexpress", "Redpack")
ESTADOS = ("EN_TRANSITO", "INCIDENCIA", "ENTREGADO")
COLS = """id, pedido_id AS pedidoId, paqueteria, guia, estado, direccion_id AS direccionId,
          fecha_envio AS fechaEnvio, fecha_entrega AS fechaEntrega"""


@bp.get("")
@requiere_admin
def listar():
    return jsonify(filas(f"SELECT {COLS} FROM envios ORDER BY id DESC LIMIT 200"))


@bp.get("/pedido/<int:pedido_id>")
@requiere_sesion
def por_pedido(pedido_id):
    p = fila("SELECT usuario_id FROM pedidos WHERE id = ?", (pedido_id,))
    e = fila(f"SELECT {COLS} FROM envios WHERE pedido_id = ?", (pedido_id,))
    if not p or not e or (g.usuario["rol"] != "admin" and p["usuario_id"] != g.usuario["id"]):
        raise ApiError(404, "Envío no encontrado")
    return jsonify(e)


@bp.post("")
@requiere_admin
def crear():
    d = cuerpo_json()
    pedido_id = entero(d.get("pedidoId"), 1, "pedidoId")
    paqueteria = d.get("paqueteria")
    if paqueteria not in PAQUETERIAS:
        raise ApiError(400, f"La paquetería debe ser una de: {', '.join(PAQUETERIAS)}.")
    with conexion(inmediata=True) as c:
        p = c.execute("SELECT estado, direccion_id FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        if not p:
            raise ApiError(404, "Pedido no encontrado")
        if p["estado"] != "EMPACADO":
            raise ApiError(409, "Solo se pueden enviar pedidos ya empacados.")
        if not p["direccion_id"]:
            raise ApiError(409, "El pedido no tiene dirección de envío.")
        guia = f"DB{pedido_id:05d}{secrets.token_hex(3).upper()}MX"
        eid = c.execute(
            """INSERT INTO envios(pedido_id, paqueteria, guia, estado, direccion_id, fecha_envio)
               VALUES (?,?,?,'EN_TRANSITO',?,?)""", (pedido_id, paqueteria, guia, p["direccion_id"], ahora())).lastrowid
        pedidos.cambiar_estado(c, pedido_id, "ENVIADO", f"Entregado a {paqueteria} · guía {guia}")
    return jsonify(fila(f"SELECT {COLS} FROM envios WHERE id = ?", (eid,))), 201


@bp.put("/<int:id>/estado")
@requiere_admin
def cambiar_estado(id):
    estado = cuerpo_json().get("estado")
    if estado not in ESTADOS:
        raise ApiError(400, f"El estado debe ser uno de: {', '.join(ESTADOS)}.")
    with conexion(inmediata=True) as c:
        e = c.execute("SELECT pedido_id, estado FROM envios WHERE id = ?", (id,)).fetchone()
        if not e:
            raise ApiError(404, "Envío no encontrado")
        if e["estado"] == "ENTREGADO":
            raise ApiError(409, "El envío ya fue entregado.")
        c.execute("UPDATE envios SET estado = ?, fecha_entrega = ? WHERE id = ?",
                  (estado, ahora() if estado == "ENTREGADO" else None, id))
        if estado == "ENTREGADO":
            pedidos.cambiar_estado(c, e["pedido_id"], "ENTREGADO", "Entregado al cliente")
        elif estado == "INCIDENCIA":
            c.execute("INSERT INTO pedido_eventos(pedido_id, estado, detalle, fecha) VALUES (?,?,?,?)",
                      (e["pedido_id"], "ENVIADO", "Incidencia en la entrega", ahora()))
    return jsonify(fila(f"SELECT {COLS} FROM envios WHERE id = ?", (id,)))
