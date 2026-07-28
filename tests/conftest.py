import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch, tmp_path):
    # SessionAuth's SECRET_KEY resolution and ensure_default_admin both
    # fail closed unless ENV=development -- see app/auth.py y
    # app/services/users.py::ensure_default_admin.
    monkeypatch.setenv("ENV", "development")
    # libracore.db es sqlite3 crudo (una conexion nueva por llamada, no un
    # engine con pool) -- ":memory:" le daria a cada llamada una base vacia
    # distinta. Un archivo temporal real por test, igual que medlibra/gestiolibra.
    monkeypatch.setenv("VENTALIBRA_LIBRACORE_DB_PATH", str(tmp_path / "ventalibra_libracore.db"))


def https_client(app) -> TestClient:
    """SessionAuth's cookie es Secure -- httpx no la reenvia sobre http
    plano, y un host de un solo label ("testserver") tiene matching de
    dominio poco confiable en el cookie jar de httpx. Mismo fix que
    gestiolibra/medlibra: base_url https con host con punto."""
    return TestClient(app, base_url="https://ventalibra.test")


@pytest.fixture
def admin_client(tmp_path):
    """App nueva contra un archivo SQLite temporal real (no :memory:, no
    mocks) + sesion logueada como el admin de bootstrap (admin/admin)."""
    db_path = str(tmp_path / "ventalibra.db")
    with https_client(create_app(db_path)) as client:
        response = client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200, response.text
        yield client


@pytest.fixture
def staff_client(admin_client: TestClient):
    """Segundo cliente logueado como staff, misma app/base que admin_client."""
    created = admin_client.post("/users", json={
        "username": "staff-1", "name": "Empleada", "password": "staff-pass", "role": "staff",
    })
    assert created.status_code == 200, created.text
    with https_client(admin_client.app) as client:
        response = client.post("/auth/login", json={"username": "staff-1", "password": "staff-pass"})
        assert response.status_code == 200, response.text
        yield client

