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


# --- corregir el ticket antes de cobrar ---------------------------------
#
# El cajero se equivoca en el mostrador: escanea de mas, tipea mal la
# cantidad, el cliente se arrepiente. Antes habia que rehacer la venta
# entera porque solo existia POST /items.


def _make_extra_item(client, name, price):
    """Item adicional: la unidad ya la creo _make_item (crearla de nuevo
    choca contra la unique de `code`)."""
    created = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price, "default_cost": "500.00"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_remove_item_recalculates_total(admin_client):
    item_id = _make_item(admin_client)
    otro_id = _make_extra_item(admin_client, "Arroz 1kg", "2000.00")
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "2"})
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": otro_id, "quantity": "1"})

    quitada = admin_client.delete(f"/sales/{sale_id}/items/0")

    assert quitada.status_code == 200, quitada.text
    assert len(quitada.json()["items"]) == 1
    assert quitada.json()["items"][0]["description_snapshot"] == "Arroz 1kg"
    assert float(quitada.json()["total"]) == 2000.0


def test_remove_last_item_leaves_empty_sale_that_cannot_be_confirmed(admin_client):
    """Quitar todo deja la venta vacia, no la cancela: el cajero puede seguir
    escaneando. Pero vacia no se puede cobrar."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})

    vacia = admin_client.delete(f"/sales/{sale_id}/items/0")
    assert vacia.status_code == 200, vacia.text
    assert vacia.json()["items"] == []
    assert float(vacia.json()["total"]) == 0.0

    rechazada = admin_client.post(
        f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"},
    )
    assert rechazada.status_code == 409


def test_remove_item_out_of_range_is_404(admin_client):
    draft = admin_client.post("/sales", json={})
    assert admin_client.delete(f"/sales/{draft.json()['id']}/items/0").status_code == 404


def test_update_item_quantity_recalculates_total(admin_client):
    item_id = _make_item(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "2"})

    corregida = admin_client.patch(f"/sales/{sale_id}/items/0", json={"quantity": "5"})

    assert corregida.status_code == 200, corregida.text
    assert float(corregida.json()["items"][0]["quantity"]) == 5.0
    assert float(corregida.json()["total"]) == 7500.0


def test_update_item_quantity_keeps_the_frozen_unit_price(admin_client):
    """El precio quedo congelado al agregar la linea (puede venir de una lista
    o haber sido puesto a mano): corregir la cantidad no lo revive."""
    item_id = _make_item(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(
        f"/sales/{sale_id}/items",
        json={"item_id": item_id, "quantity": "1", "unit_price": "999.00"},
    )

    corregida = admin_client.patch(f"/sales/{sale_id}/items/0", json={"quantity": "3"})

    assert float(corregida.json()["items"][0]["unit_price"]) == 999.0
    assert float(corregida.json()["total"]) == 2997.0


def test_update_item_quantity_rejects_zero_and_negative(admin_client):
    item_id = _make_item(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})

    assert admin_client.patch(f"/sales/{sale_id}/items/0", json={"quantity": "0"}).status_code == 409
    assert admin_client.patch(f"/sales/{sale_id}/items/0", json={"quantity": "-2"}).status_code == 409


def test_cannot_edit_a_confirmed_sale(admin_client):
    """Una venta cobrada es inmutable: corregirla es una devolucion, no una
    edicion."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "10"},
    )
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    admin_client.post(
        f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"},
    )

    assert admin_client.delete(f"/sales/{sale_id}/items/0").status_code == 409
    assert admin_client.patch(f"/sales/{sale_id}/items/0", json={"quantity": "2"}).status_code == 409
