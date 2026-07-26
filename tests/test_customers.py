def test_create_customer_without_billing_data(admin_client):
    created = admin_client.post("/customers", json={"display_name": "Juan Perez"})
    assert created.status_code == 200, created.text
    assert created.json()["cuit"] is None
    assert created.json()["condicion_iva"] is None


def test_create_customer_with_billing_data(admin_client):
    created = admin_client.post("/customers", json={
        "display_name": "Ana Gomez", "party_type": "person",
        "cuit": "27-12345678-9", "condicion_iva": "Responsable Inscripto",
    })
    assert created.status_code == 200, created.text
    customer_id = created.json()["id"]
    assert created.json()["cuit"] == "27-12345678-9"

    fetched = admin_client.get(f"/customers/{customer_id}")
    assert fetched.status_code == 200
    assert fetched.json()["condicion_iva"] == "Responsable Inscripto"

    listed = admin_client.get("/customers")
    assert any(c["id"] == customer_id for c in listed.json())


def test_get_unknown_customer_404(admin_client):
    response = admin_client.get("/customers/999")
    assert response.status_code == 404


def test_customer_list_does_not_include_suppliers(admin_client):
    admin_client.post("/suppliers", json={"display_name": "Distribuidora SA"})
    customer = admin_client.post("/customers", json={"display_name": "Ana Cliente"}).json()

    listed = admin_client.get("/customers").json()

    assert [c["id"] for c in listed] == [customer["id"]]
