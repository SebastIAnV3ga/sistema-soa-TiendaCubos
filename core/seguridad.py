"""Contraseñas y tokens (JWT HS256) usando solo la biblioteca estándar.

Conserva los verificadores del servicio de Autenticación original
(texto, bcrypt, sha256, sha512) y añade `scrypt`, que es el modo por defecto
porque no requiere dependencias externas.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Callable
from uuid import uuid4

from core.db import BASE

MODO_CONTRASENA = os.getenv("MODO_CONTRASENA", "scrypt")
ALGORITMO = "HS256"
DURACION_TOKEN = 3600  # 1 hora, como el servicio original

# ---------------------------------------------------------------- clave ----
def _clave_secreta() -> bytes:
    env = os.getenv("SECRET_KEY")
    if env:
        return env.encode()
    ruta = Path(BASE / "datos" / "secret.key")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not ruta.exists():
        ruta.write_text(secrets.token_hex(32))
    return ruta.read_text().strip().encode()


SECRET_KEY = _clave_secreta()

# ----------------------------------------------------------- contraseñas ----
def hashear_contrasena(contrasena: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(contrasena.encode(), salt=sal, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}"


def _scrypt(ingresada: str, guardada: str) -> bool:
    try:
        _, sal, h = guardada.split("$")
        calculado = hashlib.scrypt(
            ingresada.encode(), salt=base64.b64decode(sal), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(calculado, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def _texto_plano(ingresada: str, guardada: str) -> bool:
    return hmac.compare_digest(ingresada.encode(), guardada.encode())


def _bcrypt(ingresada: str, guardada: str) -> bool:
    try:
        import bcrypt  # opcional

        return bcrypt.checkpw(ingresada.encode(), guardada.encode())
    except (ImportError, ValueError):
        return False


def _sha256(ingresada: str, guardada: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(ingresada.encode()).hexdigest(), guardada)


def _sha512(ingresada: str, guardada: str) -> bool:
    return hmac.compare_digest(hashlib.sha512(ingresada.encode()).hexdigest(), guardada)


Verificador = Callable[[str, str], bool]
VERIFICADORES: dict[str, Verificador] = {
    "texto": _texto_plano,
    "bcrypt": _bcrypt,
    "sha256": _sha256,
    "sha512": _sha512,
    "scrypt": _scrypt,
}


def validar_contrasena(ingresada: str, guardada: str) -> bool:
    """Compara según MODO_CONTRASENA (para agregar otro modo, registra una
    función en VERIFICADORES)."""
    verificador = VERIFICADORES.get(MODO_CONTRASENA)
    if verificador is None:
        raise ValueError(
            f"Modo de contraseña desconocido: '{MODO_CONTRASENA}'. "
            f"Opciones disponibles: {', '.join(VERIFICADORES)}."
        )
    return verificador(ingresada, guardada)


# ------------------------------------------------------------------ JWT ----
def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _b64d(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _firmar(mensaje: str) -> str:
    return _b64(hmac.new(SECRET_KEY, mensaje.encode(), hashlib.sha256).digest())


def crear_token(datos: dict) -> str:
    cabecera = _b64(json.dumps({"alg": ALGORITMO, "typ": "JWT"}).encode())
    payload = dict(datos, exp=int(time.time()) + DURACION_TOKEN, jti=str(uuid4()))
    cuerpo = _b64(json.dumps(payload).encode())
    return f"{cabecera}.{cuerpo}.{_firmar(cabecera + '.' + cuerpo)}"


def validar_token(token: str) -> dict:
    """Devuelve el payload, o {"error": ...} si no es válido."""
    try:
        cabecera, cuerpo, firma = token.split(".")
        if not hmac.compare_digest(firma, _firmar(cabecera + "." + cuerpo)):
            return {"error": "Token inválido"}
        payload = json.loads(_b64d(cuerpo))
    except (ValueError, TypeError):
        return {"error": "Token inválido"}
    if payload.get("exp", 0) < time.time():
        return {"error": "El token ha expirado"}
    return payload


# Tokens revocados al cerrar sesión (en memoria, como el servicio original).
tokens_invalidos: set[str] = set()
