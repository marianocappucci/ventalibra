from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
