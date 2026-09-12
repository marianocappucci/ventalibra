"""El captcha ALTCHA del login, con el captcha DE VERDAD.

El comportamiento del captcha --firma, vencimiento, anti-replay-- lo prueba
libraauth (v0.40.0, ADR-014). Aca se prueba el CABLEADO de VentaLibra:

1. 🔴 **Que el router este montado con `captcha=True`.** Sin eso no hay
   `/auth/captcha` (lo contesta el catch-all de la SPA) y el login entra con
   la contrasena sola: no falla nada, simplemente no hay captcha.
2. 🔴 **Que un login sin captcha no entre aunque la clave sea buena**, y que
   el forgot-password tambien lo pida.
3. Que con el desafio resuelto se entre, y que el seed de la demo sepa
   resolverlo solo (lo corre el cron nocturno, sin nadie que tilde).

Todo el archivo va marcado con `captcha_real`: el resto de la suite corre con
el doble autouse del conftest, que acepta cualquier payload.
"""
import pytest
from altcha import Challenge, Payload, solve_challenge
from conftest import _CAPTCHA_DE_REAL, https_client
from libraauth import session_auth
from libraauth.captcha import Captcha
from libraauth.session_auth import CAPTCHA_INVALIDO
from motor_de_test import destino_dominio
from test_seed_demo import _ApiDeTest

from app.main import create_app
from scripts.seed_demo import iniciar_sesion

pytestmark = pytest.mark.captcha_real

CREDENCIALES = {"username": "admin", "password": "admin"}


@pytest.fixture
def client(tmp_path):
    """App nueva, SIN sesion: el admin de bootstrap (admin/admin) existe pero
    nadie entro todavia."""
    db_path = destino_dominio(tmp_path / "ventalibra.db")
    with https_client(create_app(db_path)) as c:
        try:
            yield c
        finally:
            # Mismo motivo que en `admin_client` del conftest: sin esto cada
            # test deja vivo el pool del engine de auth.
            motor = getattr(c.app.state, "auth_engine", None)
            if motor is not None:
                motor.dispose()


@pytest.fixture
def captcha_barato(client):
    """Un `Captcha` de costo minimo en `app.state.captcha`, que es de donde lo
    toma el `_captcha_de` real. El de produccion tarda del orden de un segundo
    por desafio; aca se resuelve en milisegundos."""
    client.app.state.captcha = Captcha(
        "clave-de-prueba", costo=1, contador_min=1, contador_rango=5,
    )


def _resolver(client) -> str:
    reto = Challenge.from_dict(client.get("/auth/captcha").json())
    solucion = solve_challenge(reto)
    assert solucion is not None
    return Payload(reto, solucion).to_base64()


def test_la_marca_deja_el_captcha_de_verdad():
    """El control del archivo: si el doble del conftest siguiera puesto, todo
    lo de abajo pasaria o fallaria por otra razon."""
    assert session_auth._captcha_de is _CAPTCHA_DE_REAL


def test_el_desafio_se_emite_y_no_se_cachea(client):
    respuesta = client.get("/auth/captcha")

    assert respuesta.status_code == 200, respuesta.text
    assert "no-store" in respuesta.headers["cache-control"]
    desafio = respuesta.json()
    assert isinstance(desafio["parameters"], dict)
    assert isinstance(desafio["signature"], str)


def test_sin_captcha_no_entra_aunque_la_clave_sea_buena(client):
    respuesta = client.post("/auth/login", json=CREDENCIALES)

    assert respuesta.status_code == 400, respuesta.text
    assert respuesta.json()["detail"] == CAPTCHA_INVALIDO


def test_un_captcha_que_no_vale_tampoco_entra(client):
    respuesta = client.post("/auth/login", json={**CREDENCIALES, "captcha": "no-es-un-payload"})

    assert respuesta.status_code == 400, respuesta.text
    assert respuesta.json()["detail"] == CAPTCHA_INVALIDO


def test_con_el_captcha_resuelto_entra(client, captcha_barato):
    respuesta = client.post("/auth/login", json={**CREDENCIALES, "captcha": _resolver(client)})

    assert respuesta.status_code == 200, respuesta.text
    assert client.get("/auth/me").status_code == 200


def test_forgot_password_tambien_pide_el_captcha(client):
    respuesta = client.post("/auth/forgot-password", json={"identificador": "admin"})

    assert respuesta.status_code == 400, respuesta.text
    assert respuesta.json()["detail"] == CAPTCHA_INVALIDO


# ── El seed de la demo ────────────────────────────────────────────────────

def test_el_seed_resuelve_el_captcha_y_entra(client, captcha_barato):
    """Lo que hace el cron de reset: login por la API, sin nadie que tilde."""
    iniciar_sesion(_ApiDeTest(client), "admin", "admin")

    assert client.get("/auth/me").status_code == 200


class _ApiSinCaptcha:
    """Una instancia sin `captcha=True`: `GET /auth/captcha` no existe."""

    def __init__(self, fallo: Exception):
        self.fallo = fallo
        self.posts: list[tuple[str, dict]] = []

    def get(self, ruta):
        raise self.fallo

    def post(self, ruta, cuerpo=None):
        self.posts.append((ruta, cuerpo))


@pytest.mark.parametrize("fallo", [
    # El catch-all de la SPA: `index.html` con 200, que no es JSON.
    ValueError("Expecting value: line 1 column 1 (char 0)"),
    RuntimeError("GET /auth/captcha -> 404: Not Found"),
], ids=["catch-all-de-la-spa", "404"])
def test_el_seed_entra_sin_captcha_si_la_instancia_no_lo_emite(fallo):
    """🔴 El seed sale de `origin/develop` y la demo corre `main`: entre el
    merge y la promocion, el seed nuevo habla con el backend viejo."""
    api = _ApiSinCaptcha(fallo)

    iniciar_sesion(api, "admin", "clave")

    assert api.posts == [("/auth/login", {"username": "admin", "password": "clave"})]


def test_el_seed_no_se_traga_otros_errores_del_desafio():
    """Un 500 o un 502 no es "no hay captcha": es la instancia rota, y el
    seed tiene que cortar ahi y no mandar un login que va a dar 400."""
    api = _ApiSinCaptcha(RuntimeError("GET /auth/captcha -> 502: Bad Gateway"))

    with pytest.raises(RuntimeError, match="502"):
        iniciar_sesion(api, "admin", "clave")
    assert api.posts == []
