"""Users -- shim sobre libraauth.

Extraído 2026-07-26 a libracore.db.usuarios (era byte-idéntico en Gestiolibra/
MedLibra/VentaLibra salvo el prefijo de env var del admin inicial, ver
wiki/analyses/auditoria-duplicacion-familia-libra.md) y **migrado el 2026-07-30
a libraauth**.

Las dos clases son idénticas en interfaz. La única diferencia es el
constructor: el de libraauth recibe un `session_factory` de SQLAlchemy, que
main.py arma sobre la base de libracore (la misma tabla de siempre).
"""
from libraauth.bootstrap import ensure_default_admin as _ensure_default_admin
from libraauth.repository import UserRepository


def ensure_default_admin(repo: UserRepository) -> None:
    _ensure_default_admin(repo, env_prefix="VENTALIBRA")
