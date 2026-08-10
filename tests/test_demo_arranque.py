"""El arranque de una instancia demo crea al visitante.

🔴 **El par que esto fija.** `incluir_demo=True` en el router hace que
`POST /auth/demo` exista; `ensure_demo_user` en el arranque hace que haya a
quién loguear. Son dos cableados distintos y **los conecta el producto, cada
uno por su lado**: que los dos miren las mismas variables de entorno no obliga
a nadie a llamar a los dos.

Estuvo roto de verdad: las tres primeras demos que se levantaron el 2026-08-06
contestaban `503 demo user not provisioned` — la ruta respondía, y respondía
que le faltaba el usuario.

Un test que sólo mirara la ruta habría pasado igual. Éste mira **el efecto del
arranque sobre la base**.
"""
import pytest


@pytest.fixture
def demo_encendida(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")


def test_el_arranque_crea_al_visitante(demo_encendida, admin_client):
    """El orden de las fixtures hace al test: `demo_encendida` **antes** que
    `admin_client`, para que el entorno esté puesto cuando se construye la app.
    Al revés, el arranque corre con la demo apagada y no siembra nada."""
    usuarios = {u["username"] for u in admin_client.get("/users").json()}

    assert "visitante" in usuarios


def test_el_visitante_no_es_admin(demo_encendida, admin_client):
    visitante = next(u for u in admin_client.get("/users").json()
                     if u["username"] == "visitante")

    assert visitante["role"] != "admin"


def test_sin_configuracion_no_se_crea_nadie_de_mas(monkeypatch, admin_client):
    """En la instancia de un cliente. Un usuario de más no rompe nada visible,
    y por eso nadie lo encontraría."""
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("DEMO_USERNAME", raising=False)

    usuarios = {u["username"] for u in admin_client.get("/users").json()}

    assert "visitante" not in usuarios
