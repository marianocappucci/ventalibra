def _abrir_turno(client, monto_inicial=0):
    """Sin turno abierto no se puede cobrar (409): toda venta tiene que caer
    dentro de un turno para que el arqueo cierre."""
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

    _abrir_turno(admin_client)
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
    _abrir_turno(admin_client)
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
    _abrir_turno(admin_client)
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

    _abrir_turno(staff_client)
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

    _abrir_turno(admin_client)
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
    _abrir_turno(admin_client)
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    admin_client.post(
        f"/sales/{sale_id}/confirm", json={"location_id": location_id, "medio_pago": "efectivo"},
    )

    assert admin_client.delete(f"/sales/{sale_id}/items/0").status_code == 409
    assert admin_client.patch(f"/sales/{sale_id}/items/0", json={"quantity": "2"}).status_code == 409


# --- cobro: pago mixto y vuelto -----------------------------------------


def _venta_lista(client, total_esperado="3000.00"):
    """Venta en borrador con stock suficiente y turno abierto, lista para
    cobrar."""
    _abrir_turno(client)
    item_id = _make_item(client)
    location_id = _make_location(client)
    client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "20"},
    )
    draft = client.post("/sales", json={})
    sale_id = draft.json()["id"]
    client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "2"})
    return sale_id, location_id


def test_cash_payment_records_the_change(admin_client):
    sale_id, location_id = _venta_lista(admin_client)

    cobrada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={
            "location_id": location_id,
            "pagos": [{"medio": "efectivo", "monto": "3000.00", "recibido": "5000.00"}],
        },
    )

    assert cobrada.status_code == 200, cobrada.text
    assert cobrada.json()["status"] == "confirmed"
    assert float(cobrada.json()["vuelto_total"]) == 2000.0
    assert float(cobrada.json()["pagos"][0]["vuelto"]) == 2000.0
    assert float(cobrada.json()["pagos"][0]["recibido"]) == 5000.0


def test_mixed_payment_is_persisted_per_method(admin_client):
    sale_id, location_id = _venta_lista(admin_client)

    cobrada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={
            "location_id": location_id,
            "pagos": [
                {"medio": "efectivo", "monto": "1000.00", "recibido": "1000.00"},
                {"medio": "tarjeta_debito", "monto": "2000.00", "referencia": "lote 7"},
            ],
        },
    )

    assert cobrada.status_code == 200, cobrada.text
    pagos = cobrada.json()["pagos"]
    assert [p["medio"] for p in pagos] == ["efectivo", "tarjeta_debito"]
    assert float(cobrada.json()["vuelto_total"]) == 0.0
    assert pagos[1]["recibido"] is None
    assert pagos[1]["referencia"] == "lote 7"

    # sobrevive a releer la venta, no solo en la respuesta del confirm
    releida = admin_client.get(f"/sales/{sale_id}")
    assert len(releida.json()["pagos"]) == 2


def test_payments_below_total_are_rejected(admin_client):
    """Cobrar de menos dejaria una venta a medio pagar: este POS no lo
    modela."""
    sale_id, location_id = _venta_lista(admin_client)

    rechazada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={
            "location_id": location_id,
            "pagos": [{"medio": "efectivo", "monto": "1000.00"}],
        },
    )

    assert rechazada.status_code == 409
    assert "no cubren el total" in rechazada.json()["detail"]


def test_received_less_than_the_payment_is_rejected(admin_client):
    sale_id, location_id = _venta_lista(admin_client)

    rechazada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={
            "location_id": location_id,
            "pagos": [{"medio": "efectivo", "monto": "3000.00", "recibido": "2000.00"}],
        },
    )

    assert rechazada.status_code == 422


def test_confirm_without_any_payment_info_is_rejected(admin_client):
    sale_id, location_id = _venta_lista(admin_client)
    sin_datos = admin_client.post(f"/sales/{sale_id}/confirm", json={"location_id": location_id})
    assert sin_datos.status_code == 422


def test_single_medio_pago_still_works_and_records_no_payments(admin_client):
    """El camino de siempre no cambia: un solo medio, sin lista de pagos."""
    sale_id, location_id = _venta_lista(admin_client)

    cobrada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo"},
    )

    assert cobrada.status_code == 200, cobrada.text
    assert cobrada.json()["pagos"] == []
    assert float(cobrada.json()["vuelto_total"]) == 0.0


def test_mixed_payment_creates_one_caja_movement_per_method(admin_client):
    """La caja tiene que poder decir cuanto entro por cada medio: es lo que
    se arquea. Un solo movimiento con el total no serviria."""
    from libracore.db import caja as db_caja

    sale_id, location_id = _venta_lista(admin_client)
    admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={
            "location_id": location_id,
            "pagos": [
                {"medio": "efectivo", "monto": "1000.00"},
                {"medio": "tarjeta_debito", "monto": "2000.00"},
            ],
        },
    )

    nuevos = [m for m in db_caja.get_caja_movimientos() if str(m["referencia"]).startswith(f"sale-{sale_id}")]
    assert len(nuevos) == 2
    assert sorted(m["medio_pago"] for m in nuevos) == ["efectivo", "tarjeta_debito"]
    assert sorted(float(m["monto"]) for m in nuevos) == [1000.0, 2000.0]


# --- turno de caja -------------------------------------------------------


def test_cobrar_sin_turno_abierto_es_rechazado(admin_client):
    """La regla que sostiene el arqueo: una venta fuera de turno seria plata
    sin control de caja."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "5"},
    )
    draft = admin_client.post("/sales", json={})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})

    rechazada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo"},
    )

    assert rechazada.status_code == 409
    assert "turno" in rechazada.json()["detail"]


def test_no_se_puede_abrir_un_turno_sobre_otro(admin_client):
    _abrir_turno(admin_client)
    segundo = admin_client.post("/shifts/open", json={"monto_inicial": 100})
    assert segundo.status_code == 409


def test_turno_actual_arranca_vacio_y_despues_reporta_el_abierto(admin_client):
    assert admin_client.get("/shifts/current").json()["turno"] is None
    tid = _abrir_turno(admin_client, monto_inicial=5000)
    actual = admin_client.get("/shifts/current").json()
    assert actual["turno"]["id"] == tid
    assert actual["turno"]["estado"] == "abierto"
    assert actual["resumen"]["total_ventas"] == 0


def test_el_cobro_queda_dentro_del_turno_y_suma_al_arqueo(admin_client):
    """El arqueo se cuenta sobre la caja: cada medio entra por separado."""
    sale_id, location_id = _venta_lista(admin_client)
    tid = admin_client.get("/shifts/current").json()["turno"]["id"]

    admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={
            "location_id": location_id,
            "pagos": [
                {"medio": "efectivo", "monto": "1000.00", "recibido": "2000.00"},
                {"medio": "tarjeta_debito", "monto": "2000.00"},
            ],
        },
    )

    resumen = admin_client.get(f"/shifts/{tid}/summary").json()["resumen"]
    assert resumen["pagos_por_medio"] == {"efectivo": 1000.0, "tarjeta_debito": 2000.0}
    # el vuelto NO entra a la caja: entraron 1000 de efectivo, no 2000
    assert resumen["efectivo_ventas"] == 1000.0
    assert resumen["total_ventas"] == 3000.0


def test_cierre_calcula_esperado_y_conserva_la_diferencia(admin_client):
    sale_id, location_id = _venta_lista(admin_client)
    tid = admin_client.get("/shifts/current").json()["turno"]["id"]
    admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "pagos": [{"medio": "efectivo", "monto": "3000.00"}]},
    )

    cerrado = admin_client.post(f"/shifts/{tid}/close", json={"monto_declarado": 2900.0})

    assert cerrado.status_code == 200, cerrado.text
    turno = cerrado.json()["turno"]
    assert turno["estado"] == "cerrado"
    assert turno["monto_esperado_cierre"] == 3000.0
    assert turno["monto_declarado_cierre"] == 2900.0
    # el resumen viene con la respuesta: despues de cerrar ya no se puede
    # reconstruir en pantalla
    assert cerrado.json()["resumen"]["efectivo_ventas"] == 3000.0


def test_no_se_cierra_dos_veces(admin_client):
    tid = _abrir_turno(admin_client)
    assert admin_client.post(f"/shifts/{tid}/close", json={"monto_declarado": 0}).status_code == 200
    repetido = admin_client.post(f"/shifts/{tid}/close", json={"monto_declarado": 0})
    assert repetido.status_code == 409


def test_despues_de_cerrar_no_se_puede_cobrar_hasta_abrir_otro(admin_client):
    sale_id, location_id = _venta_lista(admin_client)
    tid = admin_client.get("/shifts/current").json()["turno"]["id"]
    admin_client.post(f"/shifts/{tid}/close", json={"monto_declarado": 0})

    rechazada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo"},
    )
    assert rechazada.status_code == 409

    _abrir_turno(admin_client)
    cobrada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo"},
    )
    assert cobrada.status_code == 200, cobrada.text


def test_cerrar_un_turno_inexistente_es_404(admin_client):
    assert admin_client.post("/shifts/9999/close", json={"monto_declarado": 0}).status_code == 404
