"""`scripts/e2e_usuarios.py`: deja lista la instancia de los tests de navegador de dominio (`frontend/e2e/`).

Lo que fija: que cree un usuario por cada rol de la matriz (si se suma un rol y el script no lo sabe, los tests de navegador
dejarían de cubrirlo sin avisar), que se pueda correr dos veces y que el usuario creado entre de verdad con esa contraseña.
"""
import json

import pytest
from conftest import https_client

from app.permisos import ADMIN, ROLES
from scripts.e2e_usuarios import (
    CLAVE_POR_DEFECTO,
    ROLES_CON_USUARIO,
    aceptar_terminos,
    crear_usuarios_por_rol,
    usuario_de,
)
from scripts.seed_demo import Api


class _ApiDeTest(Api):
    """El `Api` de la semilla hablando con el `TestClient`: mismas rutas y mismo manejo de errores."""

    def __init__(self, client):
        self.client = client

    def _pedir(self, metodo, ruta, cuerpo=None):
        datos = json.dumps(cuerpo, default=str) if cuerpo is not None else None
        respuesta = self.client.request(
            metodo, ruta, content=datos, headers={"Content-Type": "application/json"} if datos else None)
        if respuesta.status_code >= 400:
            raise RuntimeError(f"{metodo} {ruta} -> {respuesta.status_code}: {respuesta.text[:300]}")
        return respuesta.json() if respuesta.content else None


def test_hay_un_usuario_por_cada_rol_que_no_es_admin():
    assert set(ROLES_CON_USUARIO) == set(ROLES) - {ADMIN}


def test_crea_un_usuario_por_rol_y_correrlo_dos_veces_no_falla(admin_client):
    api = _ApiDeTest(admin_client)

    primera = crear_usuarios_por_rol(api, CLAVE_POR_DEFECTO)
    segunda = crear_usuarios_por_rol(api, CLAVE_POR_DEFECTO)

    assert primera == dict.fromkeys(ROLES_CON_USUARIO, True)
    assert segunda == dict.fromkeys(ROLES_CON_USUARIO, False)


@pytest.mark.parametrize("rol", ROLES_CON_USUARIO)
def test_el_usuario_creado_entra_con_su_rol(admin_client, rol):
    crear_usuarios_por_rol(_ApiDeTest(admin_client), CLAVE_POR_DEFECTO)

    with https_client(admin_client.app) as client:
        r = client.post("/auth/login", json={"username": usuario_de(rol), "password": CLAVE_POR_DEFECTO})
        assert r.status_code == 200, r.text
        assert client.get("/auth/me").json()["role"] == rol


@pytest.mark.sin_aceptar_terminos
def test_aceptar_terminos_destraba_la_instancia_y_es_idempotente(admin_client):
    api = _ApiDeTest(admin_client)
    assert admin_client.get("/api/productos").status_code == 403

    assert aceptar_terminos(api) is True
    assert aceptar_terminos(api) is False
    assert admin_client.get("/api/productos").status_code == 200
