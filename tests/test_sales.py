def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price, "default_cost": "900.00"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _make_location(client, name="Sucursal 1"):
    created = client.post("/locations", json={"name": name})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_full_pos_flow_confirms_sale_and_decrements_stock(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "20"},
    )

    draft = admin_client.post("/sales", json={"branch_id": 1, "register_id": 1})
    assert draft.status_code == 200, draft.text
    sale_id = draft.json()["id"]
    assert draft.json()["status"] == "draft"

    with_item = admin_client.post(
        f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "3"},
    )
    assert with_item.status_code == 200, with_item.text
    assert float(with_item.json()["total"]) == 4500.0

    confirmed = admin_client.post(f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["confirmed_at"] is not None
    assert confirmed.json()["factura"] is None

    stock = admin_client.get(f"/stock/{item_id}", params={"location_id": location_id})
    assert float(stock.json()["quantity"]) == 17.0


def test_confirm_without_items_fails(admin_client):
    location_id = _make_location(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    response = admin_client.post(f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"})
    assert response.status_code == 409


def test_cannot_add_item_after_confirm(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "5"},
    )
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    admin_client.post(f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"})

    response = admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    assert response.status_code == 409


def test_add_item_with_unknown_item_id_fails(admin_client):
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    response = admin_client.post(f"/sales/{sale_id}/items", json={"item_id": 999, "quantity": "1"})
    assert response.status_code == 422


def test_get_unknown_sale_404(admin_client):
    response = admin_client.get("/sales/999")
    assert response.status_code == 404


def test_add_item_with_variant_moves_the_specific_variant_stock(admin_client):
    admin_client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    item = admin_client.post(
        "/catalog/items", json={"name": "Remera", "unit_code": "u", "default_sale_price": "5000.00"},
    ).json()
    variant_m = admin_client.post(
        f"/catalog/items/{item['id']}/variants", json={"sku": "REM-M", "name": "M"},
    ).json()
    variant_l = admin_client.post(
        f"/catalog/items/{item['id']}/variants", json={"sku": "REM-L", "name": "L"},
    ).json()
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item["id"], "location_id": location_id, "quantity_delta": "10", "variant_id": variant_m["id"]},
    )
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item["id"], "location_id": location_id, "quantity_delta": "5", "variant_id": variant_l["id"]},
    )

    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    added = admin_client.post(
        f"/sales/{sale_id}/items",
        json={"item_id": item["id"], "variant_id": variant_m["id"], "quantity": "2"},
    )
    assert added.status_code == 200, added.text
    assert added.json()["items"][0]["variant_id"] == variant_m["id"]

    admin_client.post(f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"})

    stock_m = admin_client.get(f"/stock/{item['id']}", params={"location_id": location_id, "variant_id": variant_m["id"]})
    stock_l = admin_client.get(f"/stock/{item['id']}", params={"location_id": location_id, "variant_id": variant_l["id"]})
    assert float(stock_m.json()["quantity"]) == 8.0
    assert float(stock_l.json()["quantity"]) == 5.0


def test_add_item_with_unknown_variant_fails(admin_client):
    item_id = _make_item(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]

    response = admin_client.post(
        f"/sales/{sale_id}/items", json={"item_id": item_id, "variant_id": 999, "quantity": "1"},
    )
    assert response.status_code == 422


def test_add_item_uses_resolved_price_list_over_default(admin_client):
    item_id = _make_item(admin_client)
    price_list = admin_client.post("/pricing/lists", json={"name": "Mayorista"}).json()
    admin_client.post(
        f"/pricing/items/{item_id}/prices",
        json={"price_list_id": price_list["id"], "amount": "1000.00", "valid_from": "2026-01-01T00:00:00"},
    )
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]

    added = admin_client.post(
        f"/sales/{sale_id}/items",
        json={"item_id": item_id, "quantity": "1", "price_list_id": price_list["id"]},
    )
    assert added.status_code == 200, added.text
    assert float(added.json()["items"][0]["unit_price"]) == 1000.0


def test_add_item_falls_back_to_default_sale_price_without_price_list_match(admin_client):
    item_id = _make_item(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]

    added = admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    assert added.status_code == 200, added.text
    assert float(added.json()["items"][0]["unit_price"]) == 1500.0


def test_staff_can_run_full_pos_flow(admin_client, staff_client):
    """El catalogo/stock lo carga un admin; el flujo de venta lo corre staff."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "5"},
    )

    draft = staff_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    staff_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "2"})
    confirmed = staff_client.post(f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"})
    assert confirmed.status_code == 200, confirmed.text
