def _make_item(client):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post("/catalog/items", json={"name": "Yerba 1kg", "unit_code": "u"})
    return created.json()["id"]


def _make_location(client, name="Deposito"):
    created = client.post("/locations", json={"name": name})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_current_stock_starts_at_zero(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    response = admin_client.get(f"/stock/{item_id}", params={"location_id": location_id})
    assert response.status_code == 200
    assert float(response.json()["quantity"]) == 0.0


def test_manual_adjustment_updates_current_stock(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)

    adjust = admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "10", "reason": "conteo inicial"},
    )
    assert adjust.status_code == 200, adjust.text

    response = admin_client.get(f"/stock/{item_id}", params={"location_id": location_id})
    assert float(response.json()["quantity"]) == 10.0


def test_negative_adjustment_decreases_stock(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "10"},
    )
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "-3", "reason": "rotura"},
    )
    response = admin_client.get(f"/stock/{item_id}", params={"location_id": location_id})
    assert float(response.json()["quantity"]) == 7.0
