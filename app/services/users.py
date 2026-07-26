"""Users: delegates storage to libracore.db.usuarios (shared with
Contalibra/Restolibra/Gestiolibra/MedLibra, ver wiki/entities/ventalibra.md
sección "Unificación de login").

VentaLibra ya tenía una segunda base SQLite configurada para libracore.db
(facturación/caja, ver app/services/billing.py) -- esa misma conexión ya
corre `init_core_schema()`, que crea la tabla `usuarios` aunque nadie la
usara todavía (guardaba sus propios usuarios en la base principal, tabla
`users`, ver ADR-002/ADR-003 del repo). Esta clase es un adaptador fino
que traduce el contrato externo ya establecido (id/username/name/role/
active) al esquema real de libracore (id int autoincrement/username/
nombre/email/role/activo) -- ninguna otra parte de la app (auth.py,
routers/users.py) necesitó cambiar.
"""
import os

from libracore.db import usuarios as db

ROLES = ("admin", "staff")


def _to_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "username": row["username"],
        "name": row["nombre"],
        "role": row["role"],
        "active": bool(row["activo"]),
    }


class UserRepository:
    """Adaptador sobre libracore.db.usuarios, con el mismo contrato público
    que tenía la implementación sqlite3 propia anterior."""

    def create(self, username: str, name: str, password: str, role: str) -> dict:
        if role not in ROLES:
            raise ValueError(f"invalid role: {role!r} (expected one of {ROLES})")
        uid = db.create_usuario(username=username, nombre=name, email="", password=password, role=role)
        return self.get_by_id(str(uid))

    def get_by_id(self, user_id: str) -> dict | None:
        try:
            uid = int(user_id)
        except ValueError:
            return None
        row = db.get_usuario_by_id(uid)
        return _to_dict(row) if row else None

    def get_by_username(self, username: str) -> dict | None:
        row = db.get_usuario_by_username(username)
        return _to_dict(row) if row else None

    def list(self) -> list[dict]:
        return [_to_dict(row) for row in db.get_all_usuarios()]

    def update(self, user_id: str, name: str, role: str, active: bool) -> dict:
        if role not in ROLES:
            raise ValueError(f"invalid role: {role!r} (expected one of {ROLES})")
        uid = self._require_uid(user_id)
        db.update_usuario(uid, nombre=name, email="", role=role, activo=int(active))
        return self.get_by_id(user_id)

    def update_password(self, user_id: str, new_password: str) -> None:
        uid = self._require_uid(user_id)
        db.update_usuario_password(uid, new_password)

    def delete(self, user_id: str) -> None:
        uid = self._require_uid(user_id)
        db.delete_usuario(uid)

    def _require_uid(self, user_id: str) -> int:
        """Convierte el id de la URL a int y confirma que exista -- un id no
        numérico (ej. un UUID del esquema viejo que ya no puede existir) es
        indistinguible de "no encontrado" para quien llama."""
        try:
            uid = int(user_id)
        except ValueError:
            raise KeyError(user_id)
        if db.get_usuario_by_id(uid) is None:
            raise KeyError(user_id)
        return uid

    def check_credentials(self, username: str, password: str) -> dict | None:
        """Devuelve el usuario si las credenciales son válidas y está activo
        (libracore.db.usuarios.check_usuario_credentials ya filtra activo=1
        y corre contra un hash señuelo si el username no existe, mismo
        criterio anti-timing-attack que tenía esta clase antes)."""
        row = db.check_usuario_credentials(username, password)
        return _to_dict(row) if row else None


def ensure_default_admin(repo: UserRepository) -> None:
    """Crea el admin inicial si la tabla usuarios todavía está vacía.

    Mismo criterio fail-closed que tenía esta función antes de delegar en
    libracore.db.usuarios: sin VENTALIBRA_ADMIN_PASSWORD la app no arranca
    en producción -- a diferencia de libracore.db.usuarios.ensure_admin_user()
    (usada tal cual por Contalibra/Restolibra), que en ese caso genera una
    contraseña aleatoria y solo loguea un warning. Ese comportamiento no se
    adopta acá para no relajar la postura de seguridad ya establecida.
    """
    if repo.list():
        return
    username = os.environ.get("VENTALIBRA_ADMIN_USERNAME", "admin")
    password = os.environ.get("VENTALIBRA_ADMIN_PASSWORD", "")
    if not password:
        if os.environ.get("ENV", "production") != "development":
            raise RuntimeError(
                "VENTALIBRA_ADMIN_PASSWORD no esta seteado. No se levanta la "
                "app sin una contrasena de admin inicial (setear ENV=development "
                "para desarrollo local)."
            )
        password = "admin"
    repo.create(username=username, name="Administrador", password=password, role="admin")
