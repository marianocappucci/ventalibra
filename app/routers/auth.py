import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

from ..auth import get_current_user, get_session_auth
from ..services.users import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    name: str
    role: str
    active: bool


class VerifyRequest(BaseModel):
    username: str
    password: str


class VerifyResponse(BaseModel):
    valid: bool


@router.post("/login", response_model=UserOut)
def login(data: LoginRequest, request: Request, response: Response):
    users: UserRepository = request.app.state.users
    user = users.check_credentials(data.username, data.password)
    if user is None:
        raise HTTPException(401, "invalid credentials")
    get_session_auth(request).create_session_cookie(response, user["username"])
    return user


@router.post("/logout")
def logout(request: Request, response: Response):
    get_session_auth(request).clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/verify", response_model=VerifyResponse)
def verify(
    data: VerifyRequest,
    request: Request,
    x_internal_auth: str = Header(default=""),
):
    """Stateless credential check for ventalibra_web's /docs/ login.

    Server-to-server only (shared secret DOCS_AUTH_SECRET), never creates a
    session cookie -- same contract as Contalibra/Restolibra's own
    /api/auth/verify. Fails closed if the secret isn't configured, same
    posture as SessionAuth's SECRET_KEY resolution elsewhere in this app.
    Read from the environment per-request (not at import time) so it can't
    go stale relative to whatever the process actually has configured now.
    """
    secret = os.environ.get("DOCS_AUTH_SECRET", "")
    if not secret or not hmac.compare_digest(x_internal_auth, secret):
        raise HTTPException(401, "invalid internal auth")
    users: UserRepository = request.app.state.users
    user = users.check_credentials(data.username, data.password)
    return VerifyResponse(valid=user is not None)
