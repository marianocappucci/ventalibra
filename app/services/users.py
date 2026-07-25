"""Usuarios propios de TiendaLibra (no pertenecen al dominio de LibraCommerce).

Sobre sqlite3 crudo, misma conexion que el resto de la app (ver
DECISIONS.md ADR-002/ADR-003).
"""
import os
import sqlite3
import uuid

from .. import security

ROLES = ("admin", "staff")


def _to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "role": row["role"],
        "active": bool(row["active"]),
    }


class UserRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def create(self, username: str, name: str, password: str, role: str) -> dict:
        if role not in ROLES:
            raise ValueError(f"invalid role: {role!r} (expected one of {ROLES})")
        user_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO users (id, username, name, password_hash, role, active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (user_id, username, name, security.hash_password(password), role),
        )
        self._conn.commit()
        return self.get_by_id(user_id)

    def get_by_id(self, user_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _to_dict(row) if row else None

    def get_by_username(self, username: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return _to_dict(row) if row else None

    def list(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [_to_dict(row) for row in rows]

    def update(self, user_id: str, name: str, role: str, active: bool) -> dict:
        if role not in ROLES:
            raise ValueError(f"invalid role: {role!r} (expected one of {ROLES})")
        if self.get_by_id(user_id) is None:
            raise KeyError(user_id)
        self._conn.execute(
            "UPDATE users SET name = ?, role = ?, active = ? WHERE id = ?",
            (name, role, int(active), user_id),
        )
        self._conn.commit()
        return self.get_by_id(user_id)

    def update_password(self, user_id: str, new_password: str) -> None:
        if self.get_by_id(user_id) is None:
            raise KeyError(user_id)
        self._conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (security.hash_password(new_password), user_id),
        )
        self._conn.commit()

    def delete(self, user_id: str) -> None:
        if self.get_by_id(user_id) is None:
            raise KeyError(user_id)
        self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self._conn.commit()

    def check_credentials(self, username: str, password: str) -> dict | None:
        """Devuelve el usuario si las credenciales son validas y esta activo.

        Siempre corre verify_password (contra DUMMY_PASSWORD_HASH si el
        username no existe o esta inactivo) para no filtrar por tiempo de
        respuesta si un username existe.
        """
        row = self._conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        active = row is not None and bool(row["active"])
        stored_hash = row["password_hash"] if active else security.DUMMY_PASSWORD_HASH
        password_ok = security.verify_password(stored_hash, password)
        return _to_dict(row) if (active and password_ok) else None


def ensure_default_admin(repo: UserRepository) -> None:
    """Crea el admin inicial si la tabla users todavia esta vacia.

    Mismo criterio fail-closed que gestiolibra/medlibra: sin
    TIENDALIBRA_ADMIN_PASSWORD la app no arranca en produccion.
    """
    if repo.list():
        return
    username = os.environ.get("TIENDALIBRA_ADMIN_USERNAME", "admin")
    password = os.environ.get("TIENDALIBRA_ADMIN_PASSWORD", "")
    if not password:
        if os.environ.get("ENV", "production") != "development":
            raise RuntimeError(
                "TIENDALIBRA_ADMIN_PASSWORD no esta seteado. No se levanta la "
                "app sin una contrasena de admin inicial (setear ENV=development "
                "para desarrollo local)."
            )
        password = "admin"
    repo.create(username=username, name="Administrador", password=password, role="admin")
