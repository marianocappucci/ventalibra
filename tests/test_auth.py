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


def test_staff_cannot_manage_users(staff_client):
    response = staff_client.get("/users")
    assert response.status_code == 403


def test_staff_can_use_catalog(staff_client):
    response = staff_client.get("/catalog/items")
    assert response.status_code == 200
