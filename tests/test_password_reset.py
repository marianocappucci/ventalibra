"""Recuperación de contraseña: el cableado de VentaLibra sobre libraauth.

La lógica vive probada en el motor (libraauth, 25 tests). Acá se prueba lo
que el motor no puede: que ESTE producto la tenga montada, que el link del
mail apunte a su propia pantalla, y que el flujo entero funcione contra la
app real.
"""
from conftest import https_client
from motor_de_test import destino_dominio

from app.main import create_app


def _app_con_mailbox(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "no-reply@test")
    app = create_app(destino_dominio(tmp_path / "ventalibra.db"))
    enviados = []
    app.state.password_reset._send_email = lambda **kw: enviados.append(kw)
    return app, enviados


def test_los_endpoints_estan_montados(tmp_path):
    client = https_client(create_app(destino_dominio(tmp_path / "ventalibra.db")))
    # Sin SMTP responde 503: prueba de que el endpoint existe y llega al
    # servicio (un 404 sería "no montado").
    assert client.post("/auth/forgot-password",
                       json={"identificador": "admin"}).status_code == 503


def test_forgot_password_responde_igual_exista_o_no(monkeypatch, tmp_path):
    app, enviados = _app_con_mailbox(monkeypatch, tmp_path)
    client = https_client(app)

    real = client.post("/auth/forgot-password", json={"identificador": "admin"})
    fantasma = client.post("/auth/forgot-password", json={"identificador": "nadie"})

    assert real.status_code == fantasma.status_code == 200
    assert real.json() == fantasma.json()


def test_flujo_completo(monkeypatch, tmp_path):
    app, enviados = _app_con_mailbox(monkeypatch, tmp_path)
    app.state.users.create(username="ana", name="Ana", password="vieja123",
                           role="staff", email="ana@empresa.com")
    client = https_client(app)

    assert client.post("/auth/forgot-password",
                       json={"identificador": "ana@empresa.com"}).status_code == 200
    assert len(enviados) == 1
    cuerpo = enviados[0]["cuerpo"]
    # El link lleva a la pantalla de ESTE producto.
    assert "dev.ventalibra.com.ar/reset-password?token=" in cuerpo
    token = cuerpo.split("?token=")[1].split("\n")[0].strip()

    assert client.post("/auth/reset-password",
                       json={"token": token, "new_password": "nueva-clave-1"}).status_code == 200
    assert client.post("/auth/login",
                       json={"username": "ana", "password": "nueva-clave-1"}).status_code == 200
    assert client.post("/auth/login",
                       json={"username": "ana", "password": "vieja123"}).status_code == 401
    # Un solo uso.
    assert client.post("/auth/reset-password",
                       json={"token": token, "new_password": "otra-clave-2"}).status_code == 400


def test_token_invalido_da_400(tmp_path):
    client = https_client(create_app(destino_dominio(tmp_path / "ventalibra.db")))
    assert client.post("/auth/reset-password",
                       json={"token": "inventado", "new_password": "nueva-clave-1"}).status_code == 400
