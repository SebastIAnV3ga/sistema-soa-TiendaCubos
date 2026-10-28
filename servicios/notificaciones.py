"""Servicio 20 · Notificaciones.

Original: componente visual Toast (JS). Aquí es además un servicio: guarda
las notificaciones de cada usuario (canales APP, EMAIL, SMS y PUSH,
simulados), las plantillas de los eventos de reembolso (servicio de
Reembolsos original) y la interfaz web las muestra con el Toast original
(static/js/notify.js).
"""
from flask import Blueprint, g, jsonify, request

from core.db import conexion, filas
from core.util import ApiError, ahora, bus, cuerpo_json, requiere_admin, requiere_sesion, texto

bp = Blueprint("notificaciones", __name__, url_prefix="/api/notificaciones")

EVENTOS_REEMBOLSO = {
    "SOLICITADO": "reembolso.solicitado", "APROBADO": "reembolso.aprobado",
    "RECHAZADO": "reembolso.rechazado", "COMPLETADO": "reembolso.completado",
    "FALLIDO": "reembolso.fallido",
}


def dinero(n):
    return "${:,.2f}".format(float(n))


def _destino(canal, cliente):
    if canal == "EMAIL":
        return cliente.get("email", "")
    if canal == "SMS":
        return cliente.get("telefono", "")
    if canal == "PUSH":
        return f"app://{cliente.get('id', '')}"
    return f"usuario:{cliente.get('id', '')}"


def notificar(cliente, evento, referencia, asunto, mensaje, canales=("APP",), tipo="info", c=None):
    """Registra la notificación por cada canal. `cliente` = dict con id/email/telefono.
    Si el llamador ya tiene una transacción abierta, pásala en `c`."""
    fecha = ahora()

    def guardar(cx):
        for canal in canales:
            cx.execute(
                """INSERT INTO notificaciones(usuario_id, evento, referencia, canal, destinatario, tipo,
                     asunto, mensaje, fecha) VALUES (?,?,?,?,?,?,?,?,?)""",
                (cliente.get("id"), evento, str(referencia), canal, _destino(canal, cliente), tipo, asunto,
                 mensaje[:160] if canal == "SMS" else mensaje, fecha))

    if c is not None:
        guardar(c)
    else:
        with conexion() as cx:
            guardar(cx)


# --- Plantillas de eventos de reembolso (portadas de notificacionService.js) ---
def _plantilla(evento, ctx):
    r, p, cl = ctx["reembolso"], ctx["pedido"], ctx["cliente"]
    nombre = cl.get("nombre", "cliente")
    if evento == EVENTOS_REEMBOLSO["SOLICITADO"]:
        return ("Recibimos tu solicitud de reembolso " + r["id"],
                f"Hola {nombre}, recibimos tu solicitud de reembolso por {dinero(r['monto'])} del pedido "
                f"{p['id']} ({p['producto']}). Te avisaremos cuando la procesemos.", ["APP", "EMAIL"], "info")
    if evento == EVENTOS_REEMBOLSO["APROBADO"]:
        return (f"Tu reembolso {r['id']} fue aprobado",
                f"Hola {nombre}, tu reembolso por {dinero(r['monto'])} fue aprobado y se está procesando.",
                ["APP", "EMAIL", "PUSH"], "success")
    if evento == EVENTOS_REEMBOLSO["RECHAZADO"]:
        return (f"No pudimos aprobar tu reembolso {r['id']}",
                f"Hola {nombre}, tu solicitud de reembolso fue rechazada. Motivo: {r['historial'][-1]['detalle']}.",
                ["APP", "EMAIL"], "error")
    if evento == EVENTOS_REEMBOLSO["COMPLETADO"]:
        return (f"¡Reembolso {r['id']} completado!",
                f"Hola {nombre}, depositamos {dinero(r['monto'])} a tu {r['metodoPago'].lower()}. Folio de "
                f"transacción: {r['transaccionId']}. Puede tardar de 3 a 5 días hábiles en reflejarse.",
                ["APP", "EMAIL", "SMS", "PUSH"], "success")
    if evento == EVENTOS_REEMBOLSO["FALLIDO"]:
        return (f"Hubo un problema con tu reembolso {r['id']}",
                f"Hola {nombre}, tuvimos un problema al procesar tu reembolso. Lo reintentaremos pronto; "
                "no necesitas hacer nada.", ["APP", "EMAIL"], "warning")
    return None


def _al_evento_reembolso(evento, ctx):
    if not ctx.get("cliente"):
        return
    plantilla = _plantilla(evento, ctx)
    if plantilla:
        asunto, mensaje, canales, tipo = plantilla
        notificar(ctx["cliente"], evento, ctx["reembolso"]["id"], asunto, mensaje, canales, tipo)


for _evento in EVENTOS_REEMBOLSO.values():
    bus.suscribir(_evento, _al_evento_reembolso)


# ------------------------------------------------------------------- API ----
COLS = """id, usuario_id AS usuarioId, evento, referencia, canal, destinatario, tipo, asunto, mensaje,
          estado, leida, fecha"""


@bp.get("")
@requiere_sesion
def listar():
    """Cliente: las suyas (canal APP). Admin: todas, o filtradas con ?usuarioId= y ?referencia=."""
    filtros, params = [], []
    if g.usuario["rol"] == "admin":
        if request.args.get("usuarioId", type=int) is not None:
            filtros.append("usuario_id = ?"); params.append(request.args.get("usuarioId", type=int))
    else:
        filtros += ["usuario_id = ?", "canal = 'APP'"]; params.append(g.usuario["id"])
    if request.args.get("referencia"):
        filtros.append("referencia = ?"); params.append(request.args["referencia"])
    if g.usuario["rol"] == "admin" and request.args.get("canal"):
        filtros.append("canal = ?"); params.append(request.args["canal"].upper())
    if request.args.get("noLeidas") == "1":
        filtros.append("leida = 0")
    donde = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    return jsonify(filas(f"SELECT {COLS} FROM notificaciones {donde} ORDER BY id DESC LIMIT 200", params))


@bp.post("/marcar-leidas")
@requiere_sesion
def marcar_leidas():
    d = cuerpo_json()
    ids = d.get("ids")
    with conexion() as c:
        if isinstance(ids, list) and ids:
            marcas = ",".join("?" for _ in ids)
            n = c.execute(f"UPDATE notificaciones SET leida = 1 WHERE usuario_id = ? AND id IN ({marcas})",
                          [g.usuario["id"], *[i for i in ids if type(i) is int]]).rowcount
        else:
            n = c.execute("UPDATE notificaciones SET leida = 1 WHERE usuario_id = ?", (g.usuario["id"],)).rowcount
    return jsonify(marcadas=n)


@bp.post("")
@requiere_admin
def enviar_manual():
    d = cuerpo_json()
    uid = d.get("usuarioId")
    if type(uid) is not int:
        raise ApiError(400, "El campo «usuarioId» debe ser un entero.")
    tipo = d.get("tipo", "info")
    if tipo not in ("success", "error", "warning", "info"):
        raise ApiError(400, "El tipo debe ser success, error, warning o info.")
    notificar({"id": uid}, "manual", "", texto(d.get("asunto"), "asunto", 150),
              texto(d.get("mensaje"), "mensaje", 1000), ("APP",), tipo)
    return jsonify(enviada=True), 201
