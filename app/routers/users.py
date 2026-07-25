from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services.users import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


class UserOut(BaseModel):
    id: str
    username: str
    name: str
    role: str
    active: bool


class UserCreate(BaseModel):
    username: str
    name: str
    password: str
    role: str


class UserUpdate(BaseModel):
    name: str
    role: str
    active: bool


@router.get("", response_model=list[UserOut])
def list_users(request: Request):
    users: UserRepository = request.app.state.users
    return users.list()


@router.post("", response_model=UserOut)
def create_user(data: UserCreate, request: Request):
    users: UserRepository = request.app.state.users
    if users.get_by_username(data.username) is not None:
        raise HTTPException(409, "username already exists")
    try:
        return users.create(username=data.username, name=data.name, password=data.password, role=data.role)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: str, data: UserUpdate, request: Request):
    users: UserRepository = request.app.state.users
    try:
        return users.update(user_id, name=data.name, role=data.role, active=data.active)
    except KeyError:
        raise HTTPException(404, "user not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.delete("/{user_id}")
def delete_user(user_id: str, request: Request):
    users: UserRepository = request.app.state.users
    try:
        users.delete(user_id)
    except KeyError:
        raise HTTPException(404, "user not found")
    return {"ok": True}
