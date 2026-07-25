"""Conexion SQLite unica de TiendaLibra.

Fase 1: una sola base para el esquema de LibraCommerce (catalogo, inventario,
compras, ventas) y la tabla `users` propia de TiendaLibra -- ver
DECISIONS.md ADR-002/ADR-003. No hay pool ni ORM, mismo estilo que
libracommerce/libracore.db.
"""
import sqlite3

from libracommerce.db.schema import init_schema


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    init_users_schema(conn)
    return conn


def init_users_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    conn.commit()
