"""
Token de servicio en el router de usuarios (2026-08-02).

`/users` es lo unico que el backoffice de la suite
(`admin.ventalibra.com.ar`) necesita y que no puede salir del motor: el router
de usuarios es propio de cada producto. Se le agrego
`json_api_require_admin_o_servicio`, que **amplia un permiso**, asi que lo que
importa fijar aca es el borde:

1. Sin `LIBRA_SERVICE_TOKEN` en el entorno, nada cambia.
2. Con la variable puesta, un token equivocado tampoco entra.
3. El ensanchamiento alcanza SOLO al router de usuarios y a `/admin/smtp` (que
   lo trae el motor). Todo el resto tiene que responder igual con token que sin
   el.
"""
import pytest
from conftest import https_client
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER
from motor_de_test import destino_dominio

from app.main import create_app

TOKEN = "un-token-de-servicio-de-prueba"
RUTA_USERS = "/users"

# Lo que SI acepta el token, a proposito. El resto no.
ACEPTAN_TOKEN = {RUTA_USERS, "/admin/smtp"}


@pytest.fixture
def sin_sesion(tmp_path):
    """Cliente sin loguear: es como llega el backoffice, que no es usuario."""
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as client:
        yield client


def test_sin_la_variable_el_header_no_sirve(sin_sesion, monkeypatch):
    """La garantia de adopcion: una instancia que actualiza y no toca su
    compose se comporta exactamente como antes."""
    monkeypatch.delenv(SERVICE_TOKEN_ENV, raising=False)
    r = sin_sesion.get(RUTA_USERS, headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert r.status_code == 401


def test_con_la_variable_el_token_correcto_entra(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.get(RUTA_USERS, headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert r.status_code == 200


def test_token_incorrecto_no_entra(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.get(RUTA_USERS, headers={SERVICE_TOKEN_HEADER: "otro"})
    assert r.status_code == 401


def test_sin_header_no_entra(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.get(RUTA_USERS).status_code == 401


def test_el_token_puede_dar_de_alta_un_usuario(sin_sesion, monkeypatch):
    """El caso de uso real del backoffice."""
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.post(
        RUTA_USERS,
        headers={SERVICE_TOKEN_HEADER: TOKEN},
        json={"username": "ana", "name": "Ana", "password": "clave-inicial", "role": "staff"},
    )
    # 200 y no 201: el router de usuarios de VentaLibra no declara
    # `status_code=201`, a diferencia del de los otros productos. Es una
    # divergencia real del producto, no de este test.
    assert r.status_code == 200
    assert r.json()["username"] == "ana"


def _rutas_de_control(client) -> list[str]:
    """GET sin parametros de ruta, sacadas del schema de OpenAPI.

    Del schema y no escritas a mano: una ruta inventada devuelve 404 y el test
    pasa sin haber probado nada. Paso dos veces hoy — con
    `/api/dashboard/resumen` en LibraDesk y con `/business-settings` en
    Gestiolibra.
    """
    esquema = client.app.openapi()["paths"]
    return sorted(
        p for p, ops in esquema.items()
        if "get" in ops and "{" not in p and p not in ACEPTAN_TOKEN
    )


def test_hay_rutas_de_control(sin_sesion):
    """Guarda contra el falso verde del test de abajo."""
    assert _rutas_de_control(sin_sesion), "no se encontro ninguna ruta de control"


def test_el_token_NO_cambia_nada_fuera_de_usuarios(sin_sesion, monkeypatch):
    """El ensanchamiento alcanza solo al router de usuarios.

    Se compara contra la linea de base en vez de asumir que todo lo demas da
    401: hay endpoints publicos legitimos (health, login) que dan 200 con token
    y sin el, y marcarlos seria un falso positivo. Lo que importa es que el
    token no CAMBIE la respuesta.

    Si manana alguien mueve la dependencia a `admin_only` para "simplificar",
    esto se pone rojo — que es exactamente lo que tiene que hacer.
    """
    rutas = _rutas_de_control(sin_sesion)

    monkeypatch.delenv(SERVICE_TOKEN_ENV, raising=False)
    base = {r: sin_sesion.get(r).status_code for r in rutas}

    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    con_token = {
        r: sin_sesion.get(r, headers={SERVICE_TOKEN_HEADER: TOKEN}).status_code
        for r in rutas
    }

    distintas = {r: (base[r], con_token[r]) for r in rutas if base[r] != con_token[r]}
    assert not distintas, f"el token cambio la respuesta de: {distintas}"
