"""Servicio 4 · Catálogo de Productos (original: Node + SQL Server).

Misma respuesta de `GET /api/catalogo` que el original (categorías,
productos con fotos y portada); ahora lee del maestro de productos en SQLite.
"""
import json

from flask import Blueprint, jsonify

from core.db import conexion, filas, fila
from core.util import EMAIL_RE, ApiError, ahora, cuerpo_json, entero

bp = Blueprint("catalogo", __name__, url_prefix="/api/catalogo")


def listar_catalogo():
    categorias = filas("SELECT id, nombre FROM categorias ORDER BY id")
    productos = filas(
        """SELECT p.id, p.codigo, p.nombre, p.descripcion, p.precio, p.precio_anterior AS precioAnterior,
                  p.marca, p.variantes, p.etiqueta, p.etiqueta_destacada AS etiquetaDestacada, p.categoria_id AS categoriaId,
                  c.nombre AS categoria, p.stock
           FROM productos p JOIN categorias c ON c.id = p.categoria_id
           WHERE p.activo = 1 ORDER BY p.id"""
    )
    fotos = filas(
        """SELECT f.producto_id AS productoId, f.ruta, f.texto_alternativo AS textoAlternativo
           FROM fotos_producto f JOIN productos p ON p.id = f.producto_id
           WHERE p.activo = 1 ORDER BY f.orden, f.id"""
    )
    por_producto = {}
    for f in fotos:
        por_producto.setdefault(f["productoId"], []).append(
            {"ruta": f["ruta"], "textoAlternativo": f["textoAlternativo"]})
    for p in productos:
        p["etiquetaDestacada"] = bool(p["etiquetaDestacada"])
        p["variantes"] = json.loads(p["variantes"] or "{}")
        p["fotos"] = por_producto.get(p["id"], [])
    portada = fila("SELECT valor FROM configuracion WHERE clave = 'portada'")
    return {"categorias": categorias, "productos": productos,
            "portada": portada["valor"] if portada else None}


@bp.get("")
def catalogo():
    respuesta = jsonify(listar_catalogo())
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@bp.post("/avisos-stock")
def aviso_stock():
    """El cliente deja su correo para saber cuándo vuelve un cubo agotado."""
    d = cuerpo_json()
    pid = entero(d.get("productoId"), 1, "productoId")
    email = str(d.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(400, "El correo electrónico no es válido.")
    with conexion() as c:
        p = c.execute("SELECT stock FROM productos WHERE id = ? AND activo = 1", (pid,)).fetchone()
        if not p:
            raise ApiError(404, "Producto no encontrado.")
        if p["stock"] > 0:
            raise ApiError(409, "Este cubo está disponible, no necesitas aviso.")
        c.execute("INSERT OR REPLACE INTO avisos_stock(producto_id, email, fecha, notificado) VALUES (?,?,?,0)",
                  (pid, email, ahora()))
    return jsonify({"ok": True, "mensaje": "Te avisaremos por correo cuando vuelva a haber existencias."}), 201
