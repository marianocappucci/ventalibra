"""Session auth para la API JSON de VentaLibra -- shim sobre libraauth.

Extraído 2026-07-26 a libracore.auth (era byte-idéntico en Gestiolibra/
MedLibra/VentaLibra, ver wiki/analyses/auditoria-duplicacion-familia-libra.md)
y **migrado el 2026-07-30 a `libraauth.session_auth`**: el auth salió de
LibraCore y pasó a ser un motor transversal propio, ver
wiki/entities/libraauth.md.

**Los nombres importados no cambiaron**: libraauth re-exporta exactamente la
misma API pública. La diferencia real está en main.py — su UserRepository
trabaja sobre SQLAlchemy, así que VentaLibra (que es sqlite3 crudo) sumó un
engine dedicado **sobre la base de libracore**, donde `usuarios` ya vivía.
"""
from libraauth.session_auth import (
    SessionAuth,
    json_api_get_current_user as get_current_user,
    json_api_get_session_auth as get_session_auth,
    json_api_require_admin as require_admin,
    json_api_require_role as require_role,
    json_api_require_staff as require_staff,
)

from .services.users import UserRepository


def build_session_auth(users: UserRepository) -> SessionAuth:
    return SessionAuth(
        dev_secret_fallback="ventalibra-dev-secret-not-for-prod",
        get_user_by_username=users.get_by_username,
        check_credentials=users.check_credentials,
        cookie_name="vl_session",
    )
