from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..services.users import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


class UserOut(BaseModel):
    id: str
    username: str
    name: str
    role: str
    active: bool
    email: str = ""


class UserCreate(BaseModel):
    username: str
    name: str
    password: str
    role: str
    # Opcional: el alta se puede seguir haciendo sin correo. Es la direccion a
    # la que llegaria un mail de recuperacion; VentaLibra todavia no monta
    # `/auth/forgot-password`, pero el campo es el mismo de la tabla y el ABM
    # es el unico lugar donde se carga.
    email: str = ""


class UserUpdate(BaseModel):
    name: str
    role: str
    active: bool
    # `None` = "dejalo como esta" en `UserRepository.update()`; "" = borralo.
    # El default tiene que ser None porque el toggle de activo/inactivo de la
    # grilla manda este mismo cuerpo sin tocar el correo.
    email: str | None = None


class PasswordUpdate(BaseModel):
    password: str


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
        return users.create(
            username=data.username, name=data.name, password=data.password,
            role=data.role, email=data.email,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: str, data: UserUpdate, request: Request):
    users: UserRepository = request.app.state.users
    try:
        return users.update(user_id, name=data.name, role=data.role, active=data.active, email=data.email)
    except KeyError:
        raise HTTPException(404, "user not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.put("/{user_id}/password", status_code=204)
def update_user_password(user_id: str, data: PasswordUpdate, request: Request):
    """Le pone una contrasena nueva a OTRO usuario. Exige rol admin porque el
    router entero se monta detras de `require_admin_o_servicio` (ver main.py).

    Va aparte del `PUT /{user_id}` y no como campo opcional de `UserUpdate`: el
    toggle de activo/inactivo manda ese cuerpo entero, y una contrasena que
    viaja en cada edicion de nombre o rol es superficie que no hace falta.

    No pide la contrasena actual del administrador: la sesion ya prueba quien
    es, y exigirsela lo dejaria sin poder ayudar en el unico caso para el que
    esto existe. La contraparte para cambiar la PROPIA es
    `POST /auth/change-password` (libraauth), que saca el usuario de la cookie.
    """
    users: UserRepository = request.app.state.users
    # Unico rechazo: la clave vacia. Sin minimo de longitud ni complejidad --
    # esto destraba a alguien que quedo afuera. Pero "" hasheada deja la cuenta
    # abierta con el campo en blanco, que no es una contrasena floja: es
    # ninguna.
    if not (data.password or "").strip():
        raise HTTPException(422, "la contraseña no puede estar vacía")
    try:
        users.update_password(user_id, data.password)
    except KeyError:
        raise HTTPException(404, "user not found")
    return Response(status_code=204)


@router.delete("/{user_id}")
def delete_user(user_id: str, request: Request):
    users: UserRepository = request.app.state.users
    try:
        users.delete(user_id)
    except KeyError:
        raise HTTPException(404, "user not found")
    return {"ok": True}
