"""`HEAD` tiene que contestar como `GET`, sin cuerpo: en la SPA y en `/health`.

Los monitores de uptime (uptime-kuma) y algunos navegadores y proxies sondean
con `HEAD`. FastAPI **no** deriva el `HEAD` del `GET` (Starlette sí, en sus
rutas; `APIRoute` no): con `@router.get` a secas, `HEAD /health` daba 405 con
`Allow: GET` y una instancia sana figuraba caída.

Se mide contra la app de verdad y sin sesión, con la SPA montada como en
producción (`montar_spa` sobre un `dist` de mentira): así también queda fijado
que `/health` gana sobre el catch-all y que la guarda de `/api` lo alcanza.
"""

import pytest
from conftest import https_client
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.spa import SIN_CACHE, montar_spa


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """La app armada como `app.asgi`: el mismo `dist` para la marca (que sirve `/manifest.webmanifest`) y para la SPA.

    Con el `admin_client` de la suite la marca resolvería el `dist` real del repo, que en el CI no existe, y el manifest daría 404."""
    from motor_de_test import destino_dominio

    import app.main as principal
    from app.main import create_app

    monkeypatch.setattr(principal, "frontend_dist", lambda: tmp_path)
    app = create_app(destino_dominio(tmp_path / "ventalibra.db"))
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "manifest.webmanifest").write_text("{}")
    montar_spa(app, tmp_path)
    with https_client(app) as c:
        yield c


@pytest.mark.parametrize("ruta", ["/", "/pantalla/3", "/manifest.webmanifest"])
def test_head_de_la_spa_responde_como_get_y_sin_cuerpo(cliente, ruta):
    get = cliente.get(ruta)
    head = cliente.head(ruta)
    assert get.status_code == 200
    assert head.status_code == 200, f"HEAD {ruta} dio {head.status_code} (Allow: {head.headers.get('allow')})"
    assert head.content == b""
    assert head.headers["content-type"] == get.headers["content-type"]
    assert head.headers["cache-control"] == SIN_CACHE


def test_head_de_health_lo_contesta_la_sonda_y_no_la_spa(cliente):
    """Con la SPA montada, un `HEAD /health` sin ruta propia lo atiende el catch-all: 200 con el `index.html`.

    Da verde y miente (la sonda no corrió), así que se mira el tipo de contenido: el de `/health` es JSON."""
    get = cliente.get("/health")
    head = cliente.head("/health")
    assert get.status_code == 200
    assert head.status_code == 200, f"HEAD /health dio {head.status_code} (Allow: {head.headers.get('allow')})"
    assert head.content == b""
    assert head.headers["content-type"] == get.headers["content-type"] == "application/json"


def test_la_sonda_de_salud_sola_contesta_head():
    """Sin la SPA de por medio: el router de salud declara `HEAD` él mismo (antes, 405 con `Allow: GET`)."""
    from app.routers import health

    app = FastAPI()
    app.include_router(health.router)
    cliente = TestClient(app)
    assert cliente.get("/health").status_code == 200
    head = cliente.head("/health")
    assert head.status_code == 200, f"HEAD /health dio {head.status_code} (Allow: {head.headers.get('allow')})"
    assert head.content == b""


def test_head_de_una_ruta_de_api_inexistente_es_404(cliente):
    """El control: HEAD no abre un camino por el que la API devuelva el `index.html`."""
    assert cliente.get("/api/inexistente").status_code == 404
    assert cliente.head("/api/inexistente").status_code == 404


def test_otros_metodos_siguen_sin_entrar_a_la_spa(cliente):
    assert cliente.post("/pantalla/3").status_code == 405
