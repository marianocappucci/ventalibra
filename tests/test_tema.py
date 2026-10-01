"""El tema de la suite en esta instancia (libracore ADR-012, libra-ui ADR-007/008): `GET /api/tema` público y `PUT /api/tema` del admin
o del token de servicio del backoffice.

🔴 El caso que importa para la fase 3 es el del token: `requiere("config")` a secas NO lo acepta (sólo `requiere_o_servicio`), y sin esto
la pantalla «Apariencia» del backoffice no podría empujar nada.
"""
import pytest
from conftest import https_client
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER
from motor_de_test import destino_dominio

from app.main import create_app

TEMA = {"menuActivoFondo": "#FDF2F8", "menuActivoBorde": "#F9A8D4"}
NORMALIZADO = {"menuActivoFondo": "#fdf2f8", "menuActivoBorde": "#f9a8d4"}
TOKEN = "un-token-de-servicio-de-prueba"


def _entrar(admin_client, rol):
    creado = admin_client.post("/users", json={
        "username": f"u-{rol}", "name": rol.title(), "password": "clave-larga-1", "role": rol,
    })
    assert creado.status_code == 201, creado.text
    cliente = https_client(admin_client.app)
    assert cliente.post("/auth/login", json={"username": f"u-{rol}", "password": "clave-larga-1"}).status_code == 200
    return cliente


@pytest.fixture
def sin_sesion(tmp_path):
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as client:
        yield client


def test_la_lectura_es_publica_y_arranca_vacia(sin_sesion):
    r = sin_sesion.get("/api/tema")
    assert r.status_code == 200
    assert r.json() == {"tema": {}}
    assert r.headers["cache-control"] == "no-cache"


def test_el_admin_guarda_y_cualquiera_lo_lee_sin_sesion(admin_client):
    r = admin_client.put("/api/tema", json={"tema": TEMA})
    assert r.status_code == 200, r.text
    assert r.json() == {"tema": NORMALIZADO}
    assert https_client(admin_client.app).get("/api/tema").json() == {"tema": NORMALIZADO}


def test_un_tema_vacio_restaura_los_valores_por_defecto(admin_client):
    admin_client.put("/api/tema", json={"tema": TEMA})
    assert admin_client.put("/api/tema", json={"tema": {}}).status_code == 200
    assert admin_client.get("/api/tema").json() == {"tema": {}}


@pytest.mark.parametrize("rol", ["encargado", "vendedor", "cajero", "deposito", "staff"])
def test_ningun_otro_rol_escribe_el_tema(admin_client, rol):
    cliente = _entrar(admin_client, rol)
    assert cliente.put("/api/tema", json={"tema": TEMA}).status_code == 403
    assert admin_client.get("/api/tema").json() == {"tema": {}}


def test_sin_sesion_ni_token_no_escribe(sin_sesion):
    assert sin_sesion.put("/api/tema", json={"tema": TEMA}).status_code == 401


def test_el_token_de_servicio_del_backoffice_escribe_el_tema(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.put("/api/tema", json={"tema": TEMA}, headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert r.status_code == 200, r.text
    assert sin_sesion.get("/api/tema").json() == {"tema": NORMALIZADO}


def test_un_token_equivocado_o_sin_la_variable_no_escribe(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.put("/api/tema", json={"tema": TEMA}, headers={SERVICE_TOKEN_HEADER: "otro"}).status_code == 401
    monkeypatch.delenv(SERVICE_TOKEN_ENV, raising=False)
    assert sin_sesion.put("/api/tema", json={"tema": TEMA}, headers={SERVICE_TOKEN_HEADER: TOKEN}).status_code == 401


def test_lo_que_no_tiene_la_forma_de_un_color_es_422(admin_client):
    assert admin_client.put("/api/tema", json={"tema": {"menuActivoFondo": "verde"}}).status_code == 422
    assert admin_client.get("/api/tema").json() == {"tema": {}}
