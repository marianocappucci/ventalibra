from datetime import date, timedelta


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


def _confirmed_sale(client, item_id, location_id, quantity="1"):
    draft = client.post("/sales", json={})
    sale_id = draft.json()["id"]
    client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": quantity})
    return client.post(
        f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"},
    )


def _today_range():
    today = date.today().isoformat()
    return {"date_from": today, "date_to": today}


def test_sales_report_totals_confirmed_sale(admin_client):
    item_id = _make_item(admin_client, price="1500.00")
    location_id = _make_location(admin_client)
    confirmed = _confirmed_sale(admin_client, item_id, location_id, quantity="2")
    assert confirmed.status_code == 200, confirmed.text

    response = admin_client.get("/reports/sales", params=_today_range())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_ventas"] == 1
    assert float(body["total_facturado"]) == 3000.0
    assert len(body["por_dia"]) == 1
    assert body["por_dia"][0]["cantidad"] == 1


def test_sales_report_ignores_draft_sales(admin_client):
    item_id = _make_item(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    # nunca se confirma

    response = admin_client.get("/reports/sales", params=_today_range())
    assert response.status_code == 200
    assert response.json()["total_ventas"] == 0


def test_sales_report_top_items_reflects_confirmed_sale(admin_client):
    item_id = _make_item(admin_client, name="Yerba 1kg", price="2000.00")
    location_id = _make_location(admin_client)
    _confirmed_sale(admin_client, item_id, location_id, quantity="3")

    response = admin_client.get("/reports/sales", params=_today_range())
    top_items = response.json()["top_items"]
    assert len(top_items) == 1
    assert top_items[0]["item_id"] == item_id
    assert top_items[0]["descripcion"] == "Yerba 1kg"
    assert float(top_items[0]["cantidad"]) == 3.0
    assert float(top_items[0]["total"]) == 6000.0


def test_sales_report_excludes_dates_outside_range(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _confirmed_sale(admin_client, item_id, location_id)

    yesterday = (date.today() - timedelta(days=2)).isoformat()
    day_before = (date.today() - timedelta(days=5)).isoformat()
    response = admin_client.get(
        "/reports/sales", params={"date_from": day_before, "date_to": yesterday},
    )
    assert response.json()["total_ventas"] == 0


def test_caja_report_reflects_confirmed_sale_payment(admin_client):
    item_id = _make_item(admin_client, price="500.00")
    location_id = _make_location(admin_client)
    _confirmed_sale(admin_client, item_id, location_id)

    response = admin_client.get("/reports/caja", params=_today_range())
    assert response.status_code == 200, response.text
    body = response.json()
    assert float(body["ingresos"]) == 500.0
    assert float(body["saldo_periodo"]) == 500.0


def test_stock_report_reflects_current_stock_and_flags_low_stock(admin_client):
    item_id = _make_item(admin_client, name="Arroz 1kg")
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "5"},
    )

    response = admin_client.get("/reports/stock")
    assert response.status_code == 200, response.text
    body = response.json()
    item_row = next(i for i in body["items"] if i["item_id"] == item_id)
    assert float(item_row["stock"]) == 5.0
    assert item_row not in body["low_stock"]


def test_stock_report_flags_zero_stock_as_low(admin_client):
    item_id = _make_item(admin_client, name="Fideos sin stock")

    response = admin_client.get("/reports/stock")
    assert response.status_code == 200
    body = response.json()
    low_stock_ids = [i["item_id"] for i in body["low_stock"]]
    assert item_id in low_stock_ids


def test_staff_cannot_access_reports(staff_client):
    response = staff_client.get("/reports/sales", params=_today_range())
    assert response.status_code == 403
