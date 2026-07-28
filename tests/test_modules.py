
def _abrir_turno(client, monto_inicial=0):
    """Sin turno abierto, confirmar una venta da 409: una venta fuera de
    turno seria plata sin control de caja."""
    abierto = client.post("/shifts/open", json={"monto_inicial": monto_inicial})
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["turno"]["id"]


def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price, "default_cost": "900.00"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _make_location(client, name="Deposito"):
    created = client.post("/locations", json={"name": name})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _disable(client, modulo: str) -> None:
    client.app.state.modules.set_enabled(modulo, False)


def test_all_modules_enabled_by_default(admin_client):
    assert admin_client.app.state.modules.get_all() == {"facturacion": True}


def test_billing_router_requires_facturacion_module(admin_client):
    _disable(admin_client, "facturacion")
    assert admin_client.get("/config/arca").status_code == 403


def test_confirm_sale_without_invoice_ignores_disabled_module(admin_client):
    _disable(admin_client, "facturacion")
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _abrir_turno(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    confirmed = admin_client.post(
        f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["factura"] is None


def test_confirm_sale_with_invoice_requires_facturacion_module(admin_client):
    _disable(admin_client, "facturacion")
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _abrir_turno(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    response = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo", "invoice": True},
    )
    assert response.status_code == 403


def test_confirm_sale_with_invoice_succeeds_when_module_enabled(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _abrir_turno(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    response = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo", "invoice": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["factura"] is not None


def test_catalog_stock_and_sales_are_never_gated(admin_client):
    _disable(admin_client, "facturacion")
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    assert admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "5"},
    ).status_code == 200
    _abrir_turno(admin_client)
    draft = admin_client.post("/sales", json={})
    assert draft.status_code == 200
