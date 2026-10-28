"""Servicio 22 · Inspección de Devoluciones (nuevo).

El inspector revisa el artículo devuelto:
  APTO        -> vuelve al inventario y se solicita el reembolso.
  DEFECTUOSO  -> no vuelve al inventario, pero procede el reembolso.
  NO_PROCEDE  -> se cierra sin reembolso.
"""
from flask import Blueprint, g, jsonify

from core.db import conexion, fila, filas
from core.util import ApiError, ahora, cuerpo_json, dinero, entero, requiere_admin, texto_opcional
from servicios import devoluciones, inventarios, notificaciones, reembolsos

bp = Blueprint("inspeccion_devoluciones", __name__, url_prefix="/api/inspeccion-devoluciones")

RESULTADOS = ("APTO", "DEFECTUOSO", "NO_PROCEDE")
IVA = 0.16
COLS = """i.id, i.devolucion_id AS devolucionId, i.resultado, i.observaciones, i.inspector, i.fecha,
          d.pedido_id AS pedidoId, d.sku, d.nombre, d.cantidad, d.reembolso_id AS reembolsoId"""


@bp.get("/pendientes")
@requiere_admin
def pendientes():
    return jsonify(filas(f"""SELECT {devoluciones.COLS} FROM devoluciones
                             WHERE estado = 'APROBADA' ORDER BY id"""))


@bp.get("")
@requiere_admin
def listar():
    return jsonify(filas(f"""SELECT {COLS} FROM inspecciones i JOIN devoluciones d ON d.id = i.devolucion_id
                             ORDER BY i.id DESC LIMIT 200"""))


@bp.post("")
@requiere_admin
def inspeccionar():
    d = cuerpo_json()
    dev_id = entero(d.get("devolucionId"), 1, "devolucionId")
    resultado = d.get("resultado")
    if resultado not in RESULTADOS:
        raise ApiError(400, f"El resultado debe ser uno de: {', '.join(RESULTADOS)}.")
    observaciones = texto_opcional(d.get("observaciones"), 500) or ""
    with conexion(inmediata=True) as c:
        dev = c.execute("SELECT * FROM devoluciones WHERE id = ?", (dev_id,)).fetchone()
        if not dev:
            raise ApiError(404, "Devolución no encontrada")
        if dev["estado"] != "APROBADA":
            raise ApiError(409, f"Solo se inspeccionan devoluciones APROBADAS (está {dev['estado']}).")
        c.execute("INSERT INTO inspecciones(devolucion_id, resultado, observaciones, inspector, fecha) VALUES (?,?,?,?,?)",
                  (dev_id, resultado, observaciones, g.usuario["nombre"], ahora()))
        producto = c.execute("SELECT * FROM productos WHERE codigo = ?", (dev["sku"],)).fetchone()
        precio = c.execute("SELECT precio_unitario FROM pedido_items WHERE pedido_id = ? AND sku = ?",
                           (dev["pedido_id"], dev["sku"])).fetchone()["precio_unitario"]
        if resultado == "APTO" and producto:
            inventarios.registrar_movimiento(c, dict(producto), "devolucion", dev["cantidad"], f"Devolución #{dev_id}")
        if resultado == "NO_PROCEDE":
            c.execute("UPDATE devoluciones SET estado = 'SIN_REEMBOLSO', actualizado = ? WHERE id = ?", (ahora(), dev_id))
            if dev["usuario_id"]:
                notificaciones.notificar({"id": dev["usuario_id"]}, "devolucion.sin_reembolso", dev_id,
                                         "Devolución sin reembolso",
                                         f"Tras revisar tu devolución #{dev_id}, no procede el reembolso. {observaciones}".strip(),
                                         ("APP", "EMAIL"), "warning", c=c)
        else:
            c.execute("UPDATE devoluciones SET estado = 'INSPECCIONADA', actualizado = ? WHERE id = ?", (ahora(), dev_id))
    respuesta = {"devolucionId": dev_id, "resultado": resultado, "observaciones": observaciones}
    if resultado != "NO_PROCEDE":
        # Fuera de la transacción: el servicio de Reembolsos abre las suyas.
        monto = dinero(precio * dev["cantidad"] * (1 + IVA))
        try:
            respuesta["reembolso"] = reembolsos.solicitar_reembolso(
                dev["pedido_id"], monto, dev["motivo"], f"Devolución #{dev_id}", devolucion_id=dev_id)
        except ApiError as e:
            respuesta["advertencia"] = f"La inspección se guardó, pero no se pudo solicitar el reembolso: {e}"
    return jsonify(respuesta), 201
