"""Utilidades compartidas: errores HTTP, validaciones, sesión y bus de eventos."""
import json
import re
from datetime import datetime, timezone
from functools import wraps

from flask import g, jsonify, request

from core import seguridad


class ApiError(Exception):
    def __init__(self, status, mensaje, **extra):
        super().__init__(mensaje)
        self.status = status
        self.extra = extra


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cuerpo_json() -> dict:
    cuerpo = request.get_json(silent=True)
    if cuerpo is None:
        if request.data:
            raise ApiError(400, "JSON inválido")
        return {}
    if not isinstance(cuerpo, dict):
        raise ApiError(400, "Se esperaba un objeto JSON")
    return cuerpo


def texto(valor, campo, maximo=500):
    if not isinstance(valor, str) or not valor.strip():
        raise ApiError(400, f"El campo «{campo}» es obligatorio")
    valor = valor.strip()
    if len(valor) > maximo:
        raise ApiError(400, f"El campo «{campo}» excede {maximo} caracteres")
    return valor


def texto_opcional(valor, maximo=500):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    return str(valor).strip()[:maximo]


def entero(valor, minimo, campo):
    if type(valor) is not int or valor < minimo:
        raise ApiError(400, f"El campo «{campo}» debe ser un entero mayor o igual a {minimo}")
    return valor


def numero(valor, campo, minimo=0):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < minimo:
        raise ApiError(400, f"El campo «{campo}» debe ser un número mayor o igual a {minimo}")
    return float(valor)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def dinero(x) -> float:
    return round(float(x) + 1e-9, 2)


# ------------------------------------------------------------------ sesión ----
def usuario_de_sesion():
    """Devuelve la fila del usuario de la cookie `token`, o None."""
    from core.db import fila

    token = request.cookies.get("token")
    if not token or token in seguridad.tokens_invalidos:
        return None
    payload = seguridad.validar_token(token)
    if "error" in payload or not isinstance(payload.get("id"), int):
        return None
    return fila(
        "SELECT id, nombre, apellidos, email, rol FROM usuarios WHERE id = ?", (payload["id"],)
    )


def requiere_sesion(f):
    @wraps(f)
    def interior(*a, **k):
        usuario = usuario_de_sesion()
        if usuario is None:
            raise ApiError(401, "No has iniciado sesión.")
        g.usuario = usuario
        return f(*a, **k)

    return interior


def requiere_admin(f):
    @wraps(f)
    def interior(*a, **k):
        usuario = usuario_de_sesion()
        if usuario is None:
            raise ApiError(401, "No has iniciado sesión.")
        if usuario["rol"] != "admin":
            raise ApiError(403, "Esta operación es solo para personal autorizado.")
        g.usuario = usuario
        return f(*a, **k)

    return interior


def respuesta_json(datos, status=200):
    return jsonify(datos), status


# --------------------------------------------------------------- eventos ----
class BusEventos:
    """Bus de eventos en proceso (desacopla servicios; en producción sería un
    broker como RabbitMQ o Kafka)."""

    def __init__(self):
        self._suscriptores: dict[str, list] = {}

    def suscribir(self, evento, manejador):
        self._suscriptores.setdefault(evento, []).append(manejador)

    def publicar(self, evento, ctx):
        for manejador in self._suscriptores.get(evento, []):
            try:
                manejador(evento, ctx)
            except Exception as exc:  # un suscriptor no debe romper al emisor
                print(f"[BusEventos] error en suscriptor de {evento}: {exc!r}")


bus = BusEventos()


def a_json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False)
