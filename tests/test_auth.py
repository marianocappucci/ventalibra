def test_login_success_and_me(admin_client):
    me = admin_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["role"] == "admin"


def test_login_invalid_credentials(admin_client):
    response = admin_client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_logout_clears_session(admin_client):
    assert admin_client.post("/auth/logout").status_code == 200
    assert admin_client.get("/auth/me").status_code == 401


def test_encargado_cannot_manage_users(encargado_client):
    response = encargado_client.get("/users")
    assert response.status_code == 403


def test_cajero_can_use_catalog(cajero_client):
    response = cajero_client.get("/api/productos")
    assert response.status_code == 200
