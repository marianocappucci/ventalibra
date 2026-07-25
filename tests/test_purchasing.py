def _make_item(client, name="Fideos 500g", cost="900.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": "1500.00", "default_cost": cost},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _make_location(client, name="Deposito"):
    created = client.post("/locations", json={"name": name})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _make_supplier(client, name="Distribuidora SA"):
    created = client.post("/suppliers", json={"display_name": name})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_receipt_without_order_moves_stock_and_updates_cost(admin_client):
    item_id = _make_item(admin_client, cost="900.00")
    location_id = _make_location(admin_client)
    supplier_id = _make_supplier(admin_client)

    receipt = admin_client.post("/purchase-receipts", json={"supplier_party_id": supplier_id})
    assert receipt.status_code == 200, receipt.text
    receipt_id = receipt.json()["id"]
    assert receipt.json()["status"] == "draft"

    with_item = admin_client.post(
        f"/purchase-receipts/{receipt_id}/items",
        json={"item_id": item_id, "quantity": "10", "unit_cost": "950.00"},
    )
    assert with_item.status_code == 200, with_item.text

    confirmed = admin_client.post(
        f"/purchase-receipts/{receipt_id}/confirm", json={"location_id": location_id},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["received_at"] is not None

    stock = admin_client.get(f"/stock/{item_id}", params={"location_id": location_id})
    assert float(stock.json()["quantity"]) == 10.0

    item = admin_client.get(f"/catalog/items/{item_id}")
    assert float(item.json()["default_cost"]) == 950.0


def test_receipt_linked_to_order_marks_it_partial(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    supplier_id = _make_supplier(admin_client)

    order = admin_client.post(
        "/purchase-orders", json={"supplier_party_id": supplier_id},
    )
    order_id = order.json()["id"]
    admin_client.post(
        f"/purchase-orders/{order_id}/items",
        json={"item_id": item_id, "quantity_ordered": "10", "unit_cost": "900.00"},
    )

    receipt = admin_client.post(
        "/purchase-receipts",
        json={"supplier_party_id": supplier_id, "purchase_order_id": order_id},
    )
    receipt_id = receipt.json()["id"]
    admin_client.post(
        f"/purchase-receipts/{receipt_id}/items",
        json={"item_id": item_id, "quantity": "4", "unit_cost": "900.00"},
    )
    admin_client.post(f"/purchase-receipts/{receipt_id}/confirm", json={"location_id": location_id})

    updated_order = admin_client.get(f"/purchase-orders/{order_id}")
    assert updated_order.json()["status"] == "partial"
    assert updated_order.json()["is_fully_received"] is False
    assert float(updated_order.json()["items"][0]["quantity_received"]) == 4.0


def test_receipt_linked_to_order_marks_it_received_when_complete(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    supplier_id = _make_supplier(admin_client)

    order = admin_client.post("/purchase-orders", json={"supplier_party_id": supplier_id})
    order_id = order.json()["id"]
    admin_client.post(
        f"/purchase-orders/{order_id}/items",
        json={"item_id": item_id, "quantity_ordered": "10", "unit_cost": "900.00"},
    )

    receipt = admin_client.post(
        "/purchase-receipts",
        json={"supplier_party_id": supplier_id, "purchase_order_id": order_id},
    )
    receipt_id = receipt.json()["id"]
    admin_client.post(
        f"/purchase-receipts/{receipt_id}/items",
        json={"item_id": item_id, "quantity": "10", "unit_cost": "900.00"},
    )
    admin_client.post(f"/purchase-receipts/{receipt_id}/confirm", json={"location_id": location_id})

    updated_order = admin_client.get(f"/purchase-orders/{order_id}")
    assert updated_order.json()["status"] == "received"
    assert updated_order.json()["is_fully_received"] is True


def test_confirm_without_items_fails(admin_client):
    supplier_id = _make_supplier(admin_client)
    location_id = _make_location(admin_client)
    receipt = admin_client.post("/purchase-receipts", json={"supplier_party_id": supplier_id})
    response = admin_client.post(
        f"/purchase-receipts/{receipt.json()['id']}/confirm", json={"location_id": location_id},
    )
    assert response.status_code == 409


def test_cannot_confirm_receipt_twice(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    supplier_id = _make_supplier(admin_client)
    receipt = admin_client.post("/purchase-receipts", json={"supplier_party_id": supplier_id})
    receipt_id = receipt.json()["id"]
    admin_client.post(
        f"/purchase-receipts/{receipt_id}/items",
        json={"item_id": item_id, "quantity": "1", "unit_cost": "900.00"},
    )
    admin_client.post(f"/purchase-receipts/{receipt_id}/confirm", json={"location_id": location_id})

    response = admin_client.post(
        f"/purchase-receipts/{receipt_id}/confirm", json={"location_id": location_id},
    )
    assert response.status_code == 409


def test_create_receipt_with_unknown_order_404(admin_client):
    supplier_id = _make_supplier(admin_client)
    response = admin_client.post(
        "/purchase-receipts", json={"supplier_party_id": supplier_id, "purchase_order_id": 999},
    )
    assert response.status_code == 404


def test_staff_can_run_full_purchasing_flow(admin_client, staff_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    supplier_id = _make_supplier(admin_client)

    receipt = staff_client.post("/purchase-receipts", json={"supplier_party_id": supplier_id})
    receipt_id = receipt.json()["id"]
    staff_client.post(
        f"/purchase-receipts/{receipt_id}/items",
        json={"item_id": item_id, "quantity": "5", "unit_cost": "900.00"},
    )
    confirmed = staff_client.post(
        f"/purchase-receipts/{receipt_id}/confirm", json={"location_id": location_id},
    )
    assert confirmed.status_code == 200, confirmed.text
