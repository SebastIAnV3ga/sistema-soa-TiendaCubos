"""Servicio 21 · Gestión de Devoluciones (nuevo).

Ciclo: SOLICITADA -> APROBADA | RECHAZADA -> (inspección) -> EN_REEMBOLSO -> CERRADA
                                                     \\-> SIN_REEMBOLSO
Usa las mismas reglas de plazo y motivos que el servicio de Reembolsos.
"""
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, bus, cuerpo_json, entero, requiere_admin, requiere_sesion, texto, texto_opcional
from servicios import notificaciones
from servicios.reembolsos import REGLAS

bp = Blueprint("devoluciones", __name__, url_prefix="/api/devoluciones")

COLS = """id, pedido_id AS pedidoId, usuario_id AS usuarioId, sku, nombre, cantidad, motivo, comentario,
          estado, reembolso_id AS reembolsoId, creado, actualizado"""


def _dias_desde(iso):
    f = datetime.fromisoformat(iso)
    if f.tzinfo is None:
        f = f.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - f).total_seconds() / 86400


def obtener(id_):
    return fila(f"SELECT {COLS} FROM devoluciones WHERE id = ?", (id_,))


def _puede_ver(d):
    return d and (g.usuario["rol"] == "admin" or d["usuarioId"] == g.usuario["id"])


@bp.get("/motivos")
def motivos():
    return jsonify({"motivos": REGLAS["MOTIVOS_VALIDOS"], "diasMaximos": REGLAS["DIAS_MAXIMOS"]})


@bp.post("")
@requiere_sesion
def solicitar():
    d = cuerpo_json()
    pedido_id = entero(d.get("pedidoId"), 1, "pedidoId")
    sku = texto(d.get("sku"), "sku")
    cantidad = entero(d.get("cantidad"), 1, "cantidad")
    motivo = d.get("motivo")
    if motivo not in REGLAS["MOTIVOS_VALIDOS"]:
        raise ApiError(400, f"Motivo no válido. Opciones: {', '.join(REGLAS['MOTIVOS_VALIDOS'])}.")
    comentario = texto_opcional(d.get("comentario"), 500) or ""
    with conexion(inmediata=True) as c:
        p = c.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        if not p or (g.usuario["rol"] != "admin" and p["usuario_id"] != g.usuario["id"]):
            raise ApiError(404, "Pedido no encontrado")
        if p["estado"] != "ENTREGADO":
            raise ApiError(409, "Solo se pueden devolver artículos de pedidos entregados.")
        entrega = c.execute("SELECT fecha_entrega FROM envios WHERE pedido_id = ?", (pedido_id,)).fetchone()
        referencia = (entrega["fecha_entrega"] if entrega and entrega["fecha_entrega"] else p["fecha"])
        dias = _dias_desde(referencia)
        if dias > REGLAS["DIAS_MAXIMOS"]:
            raise ApiError(409, f"Fuera del plazo de {REGLAS['DIAS_MAXIMOS']} días para devolver (han pasado {int(dias)}).")
        item = c.execute("SELECT nombre, SUM(cantidad) AS q FROM pedido_items WHERE pedido_id = ? AND sku = ? GROUP BY sku",
                         (pedido_id, sku)).fetchone()
        if not item:
            raise ApiError(404, "Ese artículo no pertenece al pedido.")
        ya = c.execute(
            "SELECT COALESCE(SUM(cantidad), 0) FROM devoluciones WHERE pedido_id = ? AND sku = ? AND estado != 'RECHAZADA'",
            (pedido_id, sku)).fetchone()[0]
        if cantidad > item["q"] - ya:
            raise ApiError(409, f"Solo quedan {item['q'] - ya} unidades de {item['nombre']} por devolver.")
        fecha = ahora()
        did = c.execute(
            """INSERT INTO devoluciones(pedido_id, usuario_id, sku, nombre, cantidad, motivo, comentario, creado, actualizado)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (pedido_id, p["usuario_id"], sku, item["nombre"], cantidad, motivo, comentario, fecha, fecha)).lastrowid
        if p["usuario_id"]:
            notificaciones.notificar({"id": p["usuario_id"]}, "devolucion.solicitada", did,
                                     "Solicitud de devolución recibida",
                                     f"Recibimos tu solicitud #{did} ({item['nombre']} ×{cantidad}). La revisaremos pronto.",
                                     ("APP", "EMAIL"), "info", c=c)
    return jsonify(obtener(did)), 201


@bp.get("")
@requiere_sesion
def listar():
    if g.usuario["rol"] == "admin":
        return jsonify(filas(f"SELECT {COLS} FROM devoluciones ORDER BY id DESC LIMIT 200"))
    return jsonify(filas(f"SELECT {COLS} FROM devoluciones WHERE usuario_id = ? ORDER BY id DESC", (g.usuario["id"],)))


@bp.get("/<int:id>")
@requiere_sesion
def uno(id):
    d = obtener(id)
    if not _puede_ver(d):
        raise ApiError(404, "Devolución no encontrada")
    return jsonify(d)


@bp.put("/<int:id>/resolucion")
@requiere_admin
def resolver(id):
    d = cuerpo_json()
    if not isinstance(d.get("aprobar"), bool):
        raise ApiError(400, "El campo «aprobar» debe ser verdadero o falso.")
    nuevo = "APROBADA" if d["aprobar"] else "RECHAZADA"
    with conexion(inmediata=True) as c:
        dev = c.execute("SELECT * FROM devoluciones WHERE id = ?", (id,)).fetchone()
        if not dev:
            raise ApiError(404, "Devolución no encontrada")
        if dev["estado"] != "SOLICITADA":
            raise ApiError(409, f"La devolución está en estado {dev['estado']}, no SOLICITADA.")
        c.execute("UPDATE devoluciones SET estado = ?, actualizado = ? WHERE id = ?", (nuevo, ahora(), id))
        if dev["usuario_id"]:
            if d["aprobar"]:
                aviso = ("Devolución aprobada", f"Aprobamos tu devolución #{id}. Envía el artículo para su inspección.", "success")
            else:
                aviso = ("Devolución rechazada", f"No pudimos aprobar tu devolución #{id}. {texto_opcional(d.get('comentario'), 300) or ''}".strip(), "error")
            notificaciones.notificar({"id": dev["usuario_id"]}, f"devolucion.{nuevo.lower()}", id, aviso[0], aviso[1],
                                     ("APP", "EMAIL"), aviso[2], c=c)
    return jsonify(obtener(id))


# Cuando el reembolso de una devolución termina, la devolución se cierra.
def _reembolso_terminado(evento, ctx):
    dev_id = ctx["reembolso"].get("devolucionId")
    if not dev_id:
        return
    estado = "CERRADA" if evento.endswith("completado") else "REEMBOLSO_RECHAZADO"
    with conexion() as c:
        c.execute("UPDATE devoluciones SET estado = ?, actualizado = ? WHERE id = ?", (estado, ahora(), dev_id))


bus.suscribir("reembolso.completado", _reembolso_terminado)
bus.suscribir("reembolso.rechazado", _reembolso_terminado)
