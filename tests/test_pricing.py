def _make_item(client, name="Fideos 500g"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": "1500.00", "default_cost": "900.00"},
    )
    return created.json()["id"]


def test_create_price_list(admin_client):
    response = admin_client.post("/pricing/lists", json={"name": "Mayorista", "is_default": True})
    assert response.status_code == 200, response.text
    assert response.json()["is_default"] is True


def test_create_second_default_price_list_fails(admin_client):
    admin_client.post("/pricing/lists", json={"name": "Mayorista", "is_default": True})
    response = admin_client.post("/pricing/lists", json={"name": "Minorista", "is_default": True})
    assert response.status_code == 409


def test_set_and_list_item_prices(admin_client):
    item_id = _make_item(admin_client)
    price_list = admin_client.post("/pricing/lists", json={"name": "General"}).json()

    created = admin_client.post(
        f"/pricing/items/{item_id}/prices",
        json={"price_list_id": price_list["id"], "amount": "1300.00", "valid_from": "2026-01-01T00:00:00"},
    )
    assert created.status_code == 200, created.text

    listed = admin_client.get(f"/pricing/items/{item_id}/prices")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert float(listed.json()[0]["amount"]) == 1300.0


def test_set_item_price_rejects_invalid_validity_window(admin_client):
    item_id = _make_item(admin_client)
    price_list = admin_client.post("/pricing/lists", json={"name": "General"}).json()

    response = admin_client.post(
        f"/pricing/items/{item_id}/prices",
        json={
            "price_list_id": price_list["id"], "amount": "1300.00",
            "valid_from": "2026-01-01T00:00:00", "valid_until": "2026-01-01T00:00:00",
        },
    )
    assert response.status_code == 422


def test_resolve_price_returns_none_without_configured_price(admin_client):
    item_id = _make_item(admin_client)
    price_list = admin_client.post("/pricing/lists", json={"name": "General"}).json()

    response = admin_client.get(
        f"/pricing/items/{item_id}/resolve", params={"price_list_id": price_list["id"]},
    )
    assert response.status_code == 200
    assert response.json()["amount"] is None


def test_resolve_price_uses_default_price_list(admin_client):
    item_id = _make_item(admin_client)
    price_list = admin_client.post("/pricing/lists", json={"name": "General", "is_default": True}).json()
    admin_client.post(
        f"/pricing/items/{item_id}/prices",
        json={"price_list_id": price_list["id"], "amount": "1300.00", "valid_from": "2026-01-01T00:00:00"},
    )

    response = admin_client.get(f"/pricing/items/{item_id}/resolve")
    assert response.status_code == 200
    assert float(response.json()["amount"]) == 1300.0
