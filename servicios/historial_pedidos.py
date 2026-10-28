"""Servicio 12 · Historial de Pedidos (nuevo): consulta de pedidos pasados."""
from datetime import date

from flask import Blueprint, g, jsonify, request

from core.db import filas
from core.util import ApiError, requiere_sesion
from servicios import pedidos

bp = Blueprint("historial_pedidos", __name__, url_prefix="/api/historial-pedidos")


def _fecha_filtro(nombre):
    valor = request.args.get(nombre)
    if not valor:
        return None
    try:
        fecha = date.fromisoformat(valor)
    except ValueError as exc:
        raise ApiError(400, f"El filtro {nombre} debe usar el formato YYYY-MM-DD.") from exc
    if fecha.isoformat() != valor:
        raise ApiError(400, f"El filtro {nombre} debe usar el formato YYYY-MM-DD.")
    return valor


@bp.get("")
@requiere_sesion
def historial():
    """Cliente: sus pedidos. Admin: todos, o los de ?usuarioId=. Filtros opcionales de estado y fecha."""
    filtros, params = [], []
    if g.usuario["rol"] == "admin":
        uid = request.args.get("usuarioId", type=int)
        if uid is not None:
            filtros.append("usuario_id = ?"); params.append(uid)
    else:
        filtros.append("usuario_id = ?"); params.append(g.usuario["id"])
    if request.args.get("estado"):
        filtros.append("estado = ?"); params.append(request.args["estado"].upper())
    desde = _fecha_filtro("desde")
    hasta = _fecha_filtro("hasta")
    if desde and hasta and desde > hasta:
        raise ApiError(400, "La fecha inicial no puede ser posterior a la fecha final.")
    if desde:
        filtros.append("substr(fecha, 1, 10) >= ?"); params.append(desde)
    if hasta:
        filtros.append("substr(fecha, 1, 10) <= ?"); params.append(hasta)
    donde = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    ids = filas(f"SELECT id FROM pedidos {donde} ORDER BY id DESC LIMIT 100", params)
    resultado = []
    for r in ids:
        p = pedidos.obtener(r["id"])
        envio = filas("SELECT paqueteria, guia, estado FROM envios WHERE pedido_id = ?", (p["id"],))
        factura = filas("SELECT folio FROM facturas WHERE pedido_id = ?", (p["id"],))
        p["envio"] = envio[0] if envio else None
        p["factura"] = factura[0]["folio"] if factura else None
        resultado.append(p)
    return jsonify(resultado)
