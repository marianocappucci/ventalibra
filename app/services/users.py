"""Users -- shim sobre libracore.db.usuarios.

Extraído 2026-07-26: el adaptador id/username/name/role/active y
ensure_default_admin() eran byte-idénticos en Gestiolibra/MedLibra/
VentaLibra salvo el prefijo de env var del admin inicial, ver
wiki/analyses/auditoria-duplicacion-familia-libra.md.
"""
from libracore.db.usuarios import UserRepository
from libracore.db.usuarios import ensure_default_admin as _ensure_default_admin


def ensure_default_admin(repo: UserRepository) -> None:
    _ensure_default_admin(repo, env_prefix="VENTALIBRA")
