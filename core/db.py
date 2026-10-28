"""Acceso a la base de datos SQLite compartida por todos los servicios.

Cada servicio es dueño de sus tablas; los demás servicios las consultan
a través de las funciones públicas de ese servicio (no escriben directo).
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("SOA_DB", BASE / "datos" / "sistema.db"))


def _abrir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


@contextmanager
def conexion(inmediata=False):
    """Transacción: confirma al salir, revierte si hay excepción.

    `inmediata=True` toma el bloqueo de escritura desde el inicio (equivale
    al BEGIN IMMEDIATE del servicio de Pedidos original) para que dos
    clientes no puedan descontar el mismo stock a la vez."""
    c = _abrir()
    try:
        if inmediata:
            c.execute("BEGIN IMMEDIATE")
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def filas(sql, params=()):
    with conexion() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def fila(sql, params=()):
    with conexion() as c:
        r = c.execute(sql, params).fetchone()
        return dict(r) if r else None


def ejecutar(sql, params=()):
    """Ejecuta una escritura y devuelve el último id insertado."""
    with conexion() as c:
        return c.execute(sql, params).lastrowid


def iniciar():
    """Crea el esquema y carga los datos de ejemplo la primera vez."""
    from core.esquema import ESQUEMA
    from core.semillas import cargar

    _abrir().execute("PRAGMA journal_mode = WAL").connection.close()
    with conexion() as c:
        c.executescript(ESQUEMA)
        hay_datos = c.execute("SELECT COUNT(*) FROM categorias").fetchone()[0]
        if not hay_datos:
            cargar(c)
