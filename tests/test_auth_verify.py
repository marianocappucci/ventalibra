"""Tests for POST /auth/verify -- the stateless check that ventalibra_web's
/docs/ login uses, protected by the shared secret DOCS_AUTH_SECRET."""
from conftest import https_client
from motor_de_test import destino_dominio

from app.main import create_app


def test_verify_without_secret_configured_returns_401(monkeypatch, admin_client):
    monkeypatch.delenv("DOCS_AUTH_SECRET", raising=False)
    response = admin_client.post(
        "/auth/verify",
        json={"username": "admin", "password": "admin"},
        headers={"X-Internal-Auth": "whatever"},
    )
    assert response.status_code == 401


def test_verify_with_wrong_secret_returns_401(monkeypatch, admin_client):
    monkeypatch.setenv("DOCS_AUTH_SECRET", "the-real-secret")
    response = admin_client.post(
        "/auth/verify",
        json={"username": "admin", "password": "admin"},
        headers={"X-Internal-Auth": "not-the-secret"},
    )
    assert response.status_code == 401


def test_verify_with_correct_secret_and_valid_credentials_returns_valid_true(monkeypatch, admin_client):
    monkeypatch.setenv("DOCS_AUTH_SECRET", "the-real-secret")
    response = admin_client.post(
        "/auth/verify",
        json={"username": "admin", "password": "admin"},
        headers={"X-Internal-Auth": "the-real-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"valid": True}


def test_verify_with_correct_secret_and_invalid_password_returns_valid_false(monkeypatch, admin_client):
    monkeypatch.setenv("DOCS_AUTH_SECRET", "the-real-secret")
    response = admin_client.post(
        "/auth/verify",
        json={"username": "admin", "password": "wrong"},
        headers={"X-Internal-Auth": "the-real-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"valid": False}


def test_verify_does_not_create_a_session(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCS_AUTH_SECRET", "the-real-secret")
    # `destino_dominio()` y no una ruta sqlite a mano: desde que la suite corre
    # sólo contra PostgreSQL (VENTALIBRA_TEST_DATABASE_URL), el dominio y
    # LibraCore tienen que caer en el MISMO motor -- `billing.configure()` crea
    # `venta_links` con una FK contra `sales(id)`, que sólo existe si las dos
    # bases son la misma. Con una ruta sqlite a mano el dominio iba a un
    # archivo propio y LibraCore (fijado por env en el autouse `_dev_env`) a
    # Postgres: `relation "sales" does not exist`.
    db_path = destino_dominio(tmp_path / "verify_no_session.db")
    client = https_client(create_app(db_path))
    response = client.post(
        "/auth/verify",
        json={"username": "admin", "password": "admin"},
        headers={"X-Internal-Auth": "the-real-secret"},
    )
    assert response.status_code == 200
    assert client.get("/auth/me").status_code == 401
