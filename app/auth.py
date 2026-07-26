"""Session auth para la API JSON de VentaLibra.

Reusa libracore.auth.SessionAuth para la mecanica de cookie firmada (mismo
patron que gestiolibra/app/auth.py y medlibra/app/auth.py). No reusa
SessionAuth.require_auth/require_role porque redirigen con 307 a "/login",
pensado para apps server-rendered -- esta es una API JSON sin paginas HTML,
asi que las dependencias propias devuelven 401/403 con cuerpo JSON.
"""
from fastapi import Depends, HTTPException, Request
from libracore.auth import SessionAuth

from .services.users import UserRepository


def build_session_auth(users: UserRepository) -> SessionAuth:
    return SessionAuth(
        dev_secret_fallback="ventalibra-dev-secret-not-for-prod",
        get_user_by_username=users.get_by_username,
        check_credentials=users.check_credentials,
        cookie_name="vl_session",
    )


def get_session_auth(request: Request) -> SessionAuth:
    return request.app.state.session_auth


def get_current_user(
    request: Request, auth: SessionAuth = Depends(get_session_auth),
) -> dict:
    username = auth.get_current_user(request)
    if username is None:
        raise HTTPException(401, "not authenticated")
    users: UserRepository = request.app.state.users
    user = users.get_by_username(username)
    if user is None or not user["active"]:
        raise HTTPException(401, "not authenticated")
    return user


def require_role(*roles: str):
    def _dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "forbidden")
        return user

    return _dependency


require_admin = require_role("admin")
require_staff = require_role("admin", "staff")
