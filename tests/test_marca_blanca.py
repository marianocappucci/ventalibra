"""La marca blanca está cableada: la instancia puede tener nombre, color y logo del revendedor (libracore ADR-092).

Lo que se mide acá es el **cableado** del producto, no el motor: que las rutas estén montadas, que escribirlas lo gate `config` (o
el token de servicio del backoffice), que el manifest le gane al catch-all de la SPA y que el mail de recuperación salga con el
nombre de la marca. El comportamiento de la marca lo prueba `libracore`.
"""
import pytest
from conftest import https_client
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER
from motor_de_test import destino_dominio

from app.main import create_app

MARCA = {"nombre": "Comercio Modelo", "nombre_corto": "Modelo", "color": "#c0392b"}
TOKEN = "un-token-de-servicio-de-prueba"


@pytest.fixture
def sin_sesion(tmp_path):
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as client:
        yield client


def test_sin_marca_la_instancia_es_la_del_producto(sin_sesion):
    r = sin_sesion.get("/api/marca")
    assert r.status_code == 200
    assert r.json()["propia"] is False
    assert r.json()["terminos_propios"] is False


def test_el_admin_carga_la_marca_y_cualquiera_la_lee_sin_sesion(admin_client):
    assert admin_client.put("/api/marca", json=MARCA).status_code == 200
    leida = https_client(admin_client.app).get("/api/marca").json()
    assert leida["propia"] is True
    assert leida["nombre"] == "Comercio Modelo"
    assert leida["color"] == "#c0392b"


@pytest.mark.parametrize("metodo", ["put", "delete"])
def test_sin_sesion_ni_token_no_se_escribe_la_marca(sin_sesion, metodo):
    r = sin_sesion.request(metodo, "/api/marca", json=MARCA if metodo == "put" else None)
    assert r.status_code == 401


def test_sin_sesion_ni_token_no_se_escriben_los_terminos_propios(sin_sesion):
    r = sin_sesion.put("/api/marca/terminos", json={"version": "r-1.0", "vigente_desde": "01-01-2026", "texto": "x"})
    assert r.status_code == 401


@pytest.mark.parametrize("rol", ["encargado", "vendedor", "cajero", "deposito"])
def test_ningun_otro_rol_escribe_la_marca(admin_client, rol):
    creado = admin_client.post("/users", json={
        "username": f"u-{rol}", "name": rol.title(), "password": "clave-larga-1", "role": rol,
    })
    assert creado.status_code == 201, creado.text
    cliente = https_client(admin_client.app)
    assert cliente.post("/auth/login", json={"username": f"u-{rol}", "password": "clave-larga-1"}).status_code == 200
    assert cliente.put("/api/marca", json=MARCA).status_code == 403
    assert admin_client.get("/api/marca").json()["propia"] is False


def test_el_token_de_servicio_del_backoffice_escribe_la_marca(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.put("/api/marca", json=MARCA, headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert r.status_code == 200, r.text
    assert sin_sesion.get("/api/marca").json()["nombre"] == "Comercio Modelo"


def test_el_manifest_es_el_de_la_marca_y_no_el_index_de_la_spa(admin_client):
    admin_client.put("/api/marca", json=MARCA)
    r = admin_client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    assert r.json()["name"] == "Comercio Modelo"


def test_el_mail_de_recuperacion_sale_con_el_nombre_de_la_marca(admin_client):
    reset = admin_client.app.state.password_reset
    assert reset.product_name == "VentaLibra"
    admin_client.put("/api/marca", json=MARCA)
    assert reset.product_name == "Comercio Modelo"
    admin_client.delete("/api/marca")
    assert reset.product_name == "VentaLibra"


def test_el_manifest_le_gana_al_catch_all_de_la_spa(tmp_path, monkeypatch):
    """🔴 Con un build, la SPA contesta `index.html` a cualquier ruta que no conozca. Si la marca se montara después,
    el navegador leería HTML como manifest. Arma la app como `app.asgi` (create_app y después montar_spa) con un build de juguete."""
    import app.main as principal
    from app.spa import montar_spa

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa-de-prueba</html>", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text('{"name": "VentaLibra", "icons": []}', encoding="utf-8")
    monkeypatch.setattr(principal, "frontend_dist", lambda: dist)

    app = create_app(destino_dominio(tmp_path / "ventalibra.db"))
    montar_spa(app, dist)
    with https_client(app) as c:
        r = c.get("/manifest.webmanifest")
        assert r.status_code == 200 and r.json()["name"] == "VentaLibra", r.text
        assert "manifest" in r.headers["content-type"]
        assert c.get("/ruta-del-cliente").text.startswith("<html>spa-de-prueba")
