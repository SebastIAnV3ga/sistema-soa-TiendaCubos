"""Servicio 23 · Reembolsos (original: Node.js, servicio-reembolso).

Mismo flujo y mismas reglas de negocio:

    SOLICITADO -> (validación) -> APROBADO -> PROCESANDO -> COMPLETADO
                              \\-> EN_REVISION (monto alto)  \\-> FALLIDO (reintentable)
                              \\-> RECHAZADO

Cada cambio de estado publica un evento en el bus; el servicio de
Notificaciones (suscrito) avisa al cliente, igual que el original. La
pasarela de pago sigue siendo una simulación con latencia y 10 % de falla
(variables TASA_FALLA y REEMBOLSO_LATENCIA_MS).
"""
import json
import os
import random
import string
import threading
import time

from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, bus, cuerpo_json, dinero, requiere_admin, requiere_sesion

bp = Blueprint("reembolsos", __name__, url_prefix="/api/reembolsos")

REGLAS = {
    "DIAS_MAXIMOS": 30,                 # ventana para pedir reembolso
    "MONTO_AUTO_APROBACION": 20000,     # arriba de esto requiere revisión manual
    "MOTIVOS_VALIDOS": ["PRODUCTO_DEFECTUOSO", "NO_RECIBIDO", "NO_COINCIDE", "ARREPENTIMIENTO", "COBRO_DUPLICADO"],
}
EVENTOS = {
    "SOLICITADO": "reembolso.solicitado", "APROBADO": "reembolso.aprobado",
    "RECHAZADO": "reembolso.rechazado", "COMPLETADO": "reembolso.completado",
    "FALLIDO": "reembolso.fallido",
}
TASA_FALLA = float(os.getenv("TASA_FALLA", "0.1"))
LATENCIA_MS = os.getenv("REEMBOLSO_LATENCIA_MS")


# ---------------------------------------------------------------- pasarela ----
def _pasarela_ejecutar(reembolso, forzar_falla=False):
    """Simula una pasarela externa (Stripe, PayPal, SPEI...)."""
    espera = float(LATENCIA_MS) / 1000 if LATENCIA_MS is not None else 0.8 + random.random() * 0.7
    time.sleep(espera)
    if forzar_falla or random.random() < TASA_FALLA:
        raise RuntimeError(f"La pasarela {reembolso['metodoPago']} rechazó la transacción (timeout del banco emisor)")
    return {"transaccionId": "TXN-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))}


# ------------------------------------------------------------- persistencia ----
def _publico(r):
    return {
        "id": r["id"], "pedidoId": r["pedido_id"], "clienteId": r["cliente_id"], "monto": r["monto"],
        "metodoPago": r["metodo_pago"], "motivo": r["motivo"], "comentario": r["comentario"],
        "estado": r["estado"], "transaccionId": r["transaccion_id"], "intentos": r["intentos"],
        "creado": r["creado"], "actualizado": r["actualizado"], "historial": json.loads(r["historial"]),
        "devolucionId": r["devolucion_id"],
    }


def obtener(id_):
    r = fila("SELECT * FROM reembolsos WHERE id = ?", (id_,))
    if not r:
        raise ApiError(404, f"Reembolso {id_} no encontrado")
    return _publico(r)


def _historial(c, id_, estado, detalle):
    fecha = ahora()
    r = c.execute("SELECT historial FROM reembolsos WHERE id = ?", (id_,)).fetchone()
    h = json.loads(r["historial"])
    h.append({"estado": estado, "detalle": detalle, "fecha": fecha})
    c.execute("UPDATE reembolsos SET estado = ?, actualizado = ?, historial = ? WHERE id = ?",
              (estado, fecha, json.dumps(h, ensure_ascii=False), id_))


def _contexto(id_):
    r = obtener(id_)
    p = fila("SELECT * FROM pedidos WHERE id = ?", (r["pedidoId"],)) or {}
    resumen = ", ".join(f"{i['nombre']} ×{i['cantidad']}" for i in filas(
        "SELECT nombre, cantidad FROM pedido_items WHERE pedido_id = ?", (r["pedidoId"],)))
    return {
        "reembolso": r,
        "pedido": {"id": r["pedidoId"], "producto": resumen, "total": p.get("total")},
        "cliente": {"id": p.get("usuario_id"), "nombre": p.get("cliente_nombre", ""),
                    "email": p.get("cliente_email", ""), "telefono": p.get("cliente_telefono", "")},
    }


def _publicar(clave, id_):
    bus.publicar(EVENTOS[clave], _contexto(id_))


def _en_segundo_plano(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


# ------------------------------------------------------------------ lógica ----
def _validar(pedido, monto, motivo):
    """Valida la solicitud contra las reglas de negocio. Devuelve (ok, motivo)."""
    from datetime import datetime, timezone

    fecha = datetime.fromisoformat(pedido["fecha"])
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    dias = (datetime.now(timezone.utc) - fecha).total_seconds() / 86400
    if dias > REGLAS["DIAS_MAXIMOS"]:
        return False, f"Fuera de la ventana de {REGLAS['DIAS_MAXIMOS']} días (han pasado {int(dias)})"
    disponible = dinero(pedido["total"] - pedido["reembolsado"])
    if monto > disponible:
        return False, f"El monto excede lo disponible para reembolsar (${disponible:,.2f})"
    if motivo not in REGLAS["MOTIVOS_VALIDOS"]:
        return False, f"Motivo no válido: {motivo}"
    return True, None


def solicitar_reembolso(pedido_id, monto=None, motivo=None, comentario="", forzar_falla=False, devolucion_id=None):
    """Crea la solicitud y la procesa en segundo plano. Devuelve el reembolso en su estado inicial."""
    with conexion(inmediata=True) as c:
        pedido = c.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        if not pedido:
            raise ApiError(404, f"Pedido {pedido_id} no encontrado")
        if pedido["estado"] in ("CREADO", "CANCELADO"):
            raise ApiError(409, f"El pedido {pedido_id} no tiene un pago confirmado")
        if monto is None or monto == "":
            monto = dinero(pedido["total"] - pedido["reembolsado"])
        if isinstance(monto, bool) or not isinstance(monto, (int, float)) or monto <= 0:
            raise ApiError(400, "El monto debe ser un número mayor a 0")
        en_curso = c.execute(
            "SELECT id FROM reembolsos WHERE pedido_id = ? AND estado IN ('SOLICITADO','APROBADO','PROCESANDO','EN_REVISION')",
            (pedido_id,)).fetchone()
        if en_curso:
            raise ApiError(409, f"Ya existe un reembolso en curso para {pedido_id} ({en_curso['id']})")
        siguiente = (c.execute("SELECT COUNT(*) FROM reembolsos").fetchone()[0]) + 1
        id_ = f"REE-{siguiente:04d}"
        c.execute(
            """INSERT INTO reembolsos(id, pedido_id, cliente_id, monto, metodo_pago, motivo, comentario,
                 creado, forzar_falla, devolucion_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (id_, pedido_id, pedido["usuario_id"], dinero(monto), pedido["metodo_pago"] or "TARJETA", motivo or "",
             comentario or "", ahora(), 1 if forzar_falla else 0, devolucion_id))
        _historial(c, id_, "SOLICITADO", "Solicitud recibida")
        if devolucion_id:
            c.execute("UPDATE devoluciones SET reembolso_id = ?, estado = 'EN_REEMBOLSO', actualizado = ? WHERE id = ?",
                      (id_, ahora(), devolucion_id))
    _publicar("SOLICITADO", id_)
    _en_segundo_plano(_procesar, id_)
    return obtener(id_)


def _procesar(id_):
    """Valida y, si procede, ejecuta el reembolso con la pasarela."""
    r = fila("SELECT * FROM reembolsos WHERE id = ?", (id_,))
    pedido = fila("SELECT * FROM pedidos WHERE id = ?", (r["pedido_id"],))
    if r["estado"] == "SOLICITADO":
        ok, motivo = _validar(pedido, r["monto"], r["motivo"])
        if not ok:
            with conexion() as c:
                _historial(c, id_, "RECHAZADO", motivo)
            _publicar("RECHAZADO", id_)
            return
        if r["monto"] > REGLAS["MONTO_AUTO_APROBACION"]:
            with conexion() as c:
                _historial(c, id_, "EN_REVISION",
                           f"Monto mayor a ${REGLAS['MONTO_AUTO_APROBACION']}: requiere aprobación manual")
            return
        with conexion() as c:
            _historial(c, id_, "APROBADO", "Aprobado automáticamente por reglas de negocio")
        _publicar("APROBADO", id_)
    _ejecutar(id_)


def _ejecutar(id_):
    with conexion() as c:
        r = c.execute("SELECT * FROM reembolsos WHERE id = ?", (id_,)).fetchone()
        _historial(c, id_, "PROCESANDO", f"Enviando a pasarela {r['metodo_pago']}")
        c.execute("UPDATE reembolsos SET intentos = intentos + 1 WHERE id = ?", (id_,))
    publico = obtener(id_)
    try:
        tx = _pasarela_ejecutar(publico, forzar_falla=bool(r["forzar_falla"]))
    except RuntimeError as err:
        with conexion() as c:
            c.execute("UPDATE reembolsos SET forzar_falla = 0 WHERE id = ?", (id_,))
            _historial(c, id_, "FALLIDO", str(err))
        _publicar("FALLIDO", id_)
        return
    with conexion() as c:
        c.execute("UPDATE reembolsos SET forzar_falla = 0, transaccion_id = ? WHERE id = ?", (tx["transaccionId"], id_))
        c.execute("UPDATE pedidos SET reembolsado = ROUND(reembolsado + ?, 2) WHERE id = ?", (r["monto"], r["pedido_id"]))
        _historial(c, id_, "COMPLETADO", f"Transacción {tx['transaccionId']} confirmada")
    _publicar("COMPLETADO", id_)


def aprobar_manual(id_, aprobar=True):
    with conexion(inmediata=True) as c:
        r = c.execute("SELECT estado FROM reembolsos WHERE id = ?", (id_,)).fetchone()
        if not r:
            raise ApiError(404, f"Reembolso {id_} no encontrado")
        if r["estado"] != "EN_REVISION":
            raise ApiError(409, f"El reembolso está en estado {r['estado']}, no EN_REVISION")
        if not aprobar:
            _historial(c, id_, "RECHAZADO", "Rechazado por un supervisor")
        else:
            _historial(c, id_, "APROBADO", "Aprobado manualmente por un supervisor")
    _publicar("APROBADO" if aprobar else "RECHAZADO", id_)
    if aprobar:
        _en_segundo_plano(_ejecutar, id_)
    return obtener(id_)


def reintentar(id_):
    r = fila("SELECT estado FROM reembolsos WHERE id = ?", (id_,))
    if not r:
        raise ApiError(404, f"Reembolso {id_} no encontrado")
    if r["estado"] != "FALLIDO":
        raise ApiError(409, "Solo se pueden reintentar reembolsos FALLIDOS")
    _en_segundo_plano(_ejecutar, id_)
    return obtener(id_)


# --------------------------------------------------------------------- API ----
@bp.get("/reglas")
def reglas():
    return jsonify(REGLAS)


@bp.get("/pedidos")
@requiere_admin
def pedidos_reembolsables():
    return jsonify(filas(
        """SELECT id, usuario_id AS clienteId, cliente_nombre AS cliente, total, reembolsado, estado, fecha,
                  metodo_pago AS metodoPago FROM pedidos WHERE estado NOT IN ('CREADO','CANCELADO') ORDER BY id DESC"""))


@bp.get("")
@requiere_sesion
def listar():
    if g.usuario["rol"] == "admin":
        filas_ = filas("SELECT * FROM reembolsos ORDER BY rowid DESC")
    else:
        filas_ = filas("SELECT * FROM reembolsos WHERE cliente_id = ? ORDER BY rowid DESC", (g.usuario["id"],))
    return jsonify([_publico(r) for r in filas_])


@bp.post("")
@requiere_admin
def solicitar():
    d = cuerpo_json()
    if type(d.get("pedidoId")) is not int:
        raise ApiError(400, "El campo «pedidoId» debe ser un entero.")
    return jsonify(solicitar_reembolso(d["pedidoId"], d.get("monto"), d.get("motivo"), d.get("comentario", ""),
                                       bool(d.get("forzarFalla")))), 202


@bp.get("/<id_>")
@requiere_sesion
def uno(id_):
    r = obtener(id_)
    if g.usuario["rol"] != "admin" and r["clienteId"] != g.usuario["id"]:
        raise ApiError(404, f"Reembolso {id_} no encontrado")
    return jsonify(r)


@bp.post("/<id_>/aprobar")
@requiere_admin
def aprobar(id_):
    return jsonify(aprobar_manual(id_, True))


@bp.post("/<id_>/rechazar")
@requiere_admin
def rechazar(id_):
    return jsonify(aprobar_manual(id_, False))


@bp.post("/<id_>/reintentar")
@requiere_admin
def r_reintentar(id_):
    return jsonify(reintentar(id_)), 202
