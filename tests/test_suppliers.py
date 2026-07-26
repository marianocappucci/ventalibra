def test_create_and_list_supplier(admin_client):
    created = admin_client.post("/suppliers", json={"display_name": "Distribuidora SA", "tax_id": "30-12345678-9"})
    assert created.status_code == 200, created.text
    supplier_id = created.json()["id"]
    assert created.json()["party_type"] == "organization"

    listed = admin_client.get("/suppliers")
    assert listed.status_code == 200
    assert any(s["id"] == supplier_id for s in listed.json())

    fetched = admin_client.get(f"/suppliers/{supplier_id}")
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "Distribuidora SA"


def test_get_unknown_supplier_404(admin_client):
    response = admin_client.get("/suppliers/999")
    assert response.status_code == 404


def test_invalid_party_type_422(admin_client):
    response = admin_client.post("/suppliers", json={"display_name": "X", "party_type": "bogus"})
    assert response.status_code == 422


def test_supplier_list_does_not_include_customers(admin_client):
    admin_client.post("/customers", json={"display_name": "Ana Cliente"})
    supplier = admin_client.post("/suppliers", json={"display_name": "Distribuidora SA"}).json()

    listed = admin_client.get("/suppliers").json()

    assert [s["id"] for s in listed] == [supplier["id"]]
