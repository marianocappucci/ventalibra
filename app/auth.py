"""Session auth para la API JSON de VentaLibra -- shim sobre libracore.auth.

Extraído 2026-07-26: reusa libracore.auth.SessionAuth para la mecánica de
cookie firmada, y las dependencias json_api_* de libracore.auth (401/403
JSON sin redirect, pensadas para APIs JSON puras sin página de login
server-rendered) -- eran byte-idénticas en Gestiolibra/MedLibra/VentaLibra,
ver wiki/analyses/auditoria-duplicacion-familia-libra.md.
"""
from libracore.auth import (
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
