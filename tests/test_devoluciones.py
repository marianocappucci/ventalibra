"""Anulación y devolución.

Lo que ordena estos tests: **deshacer una venta tiene que dejar todo como
antes** — el stock de vuelta en el depósito y la plata fuera de la caja — y
no puede ejecutarse dos veces. Un reintento que reponga stock por segunda
vez inventa mercadería que no existe.
"""
from decimal import Decimal


def _abrir_turno(client):
    abierto = client.post("/shifts/open", json={"monto_inicial": 0})
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["turno"]["id"]


def _make_item(client, name="Yerba 1kg", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _make_location(client):
    return client.post("/locations", json={"name": "Sucursal 1"}).json()["id"]


def _con_stock(client, item_id, location_id, cantidad="20"):
    client.post("/stock/adjustments", json={
        "item_id": item_id, "location_id": location_id, "quantity_delta": cantidad,
    })


def _stock(client, item_id, location_id) -> Decimal:
    return Decimal(client.get(f"/stock/{item_id}", params={"location_id": location_id}).json()["quantity"])


def _venta(client, item_id, location_id, cantidad="2", pagos=None, customer_id=None):
    borrador = client.post("/sales", json={"customer_party_id": customer_id})
    sale_id = borrador.json()["id"]
    linea = client.post(
        f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": cantidad},
    )
    confirmada = client.post(f"/sales/{sale_id}/confirm", json={
        "location_id": location_id,
        "pagos": pagos or [{"medio": "efectivo", "monto": linea.json()["total"]}],
    })
    assert confirmada.status_code == 200, confirmada.text
    return sale_id


# ── Anulación ────────────────────────────────────────────────────────────────

def test_anular_repone_el_stock_y_saca_la_plata_de_la_caja(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "20")
    turno_id = _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "3")

    assert _stock(admin_client, item_id, location_id) == 17
    assert Decimal(str(
        admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]["total_ventas"]
    )) == 4500

    anulada = admin_client.post(f"/sales/{sale_id}/cancel")
    assert anulada.status_code == 200, anulada.text
    assert anulada.json()["status"] == "cancelled"

    # Todo como antes: la mercadería volvió y la plata salió.
    assert _stock(admin_client, item_id, location_id) == 20
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 0


def test_anular_dos_veces_no_repone_dos_veces(admin_client):
    """El reintento del botón no puede inventar mercadería."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "2")

    admin_client.post(f"/sales/{sale_id}/cancel")
    admin_client.post(f"/sales/{sale_id}/cancel")

    assert _stock(admin_client, item_id, location_id) == 10


def test_anular_una_venta_fiada_le_baja_la_deuda_al_cliente(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    _abrir_turno(admin_client)
    cliente = admin_client.post("/customers", json={"display_name": "Vecina"}).json()["id"]
    sale_id = _venta(admin_client, item_id, location_id, "2",
                     pagos=[{"medio": "cuenta_corriente", "monto": "3000"}],
                     customer_id=cliente)
    assert Decimal(admin_client.get(f"/accounts/{cliente}").json()["saldo"]) == 3000

    admin_client.post(f"/sales/{sale_id}/cancel")

    assert Decimal(admin_client.get(f"/accounts/{cliente}").json()["saldo"]) == 0


def test_no_se_anula_un_borrador(admin_client):
    borrador = admin_client.post("/sales", json={})
    respuesta = admin_client.post(f"/sales/{borrador.json()['id']}/cancel")
    assert respuesta.status_code == 409


def test_anular_una_venta_inexistente_es_404(admin_client):
    assert admin_client.post("/sales/9999/cancel").status_code == 404


# ── Devolución parcial ───────────────────────────────────────────────────────

def test_devolver_una_parte_repone_solo_esa_parte(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "20")
    turno_id = _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "5")
    assert _stock(admin_client, item_id, location_id) == 15

    devuelta = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "2"}], "location_id": location_id,
    })
    assert devuelta.status_code == 200, devuelta.text
    assert devuelta.json()["status"] == "partially_returned"

    assert _stock(admin_client, item_id, location_id) == 17
    # Se reintegraron 2 x 1500 = 3000 de los 7500 cobrados.
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 4500


def test_devolver_todo_deja_la_venta_como_devuelta(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "2")

    devuelta = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "2"}], "location_id": location_id,
    })

    assert devuelta.json()["status"] == "returned"
    assert _stock(admin_client, item_id, location_id) == 10


def test_no_se_puede_devolver_mas_de_lo_vendido(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "2")

    respuesta = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "5"}], "location_id": location_id,
    })
    assert respuesta.status_code == 422
    # Y el stock no se movió por el intento.
    assert _stock(admin_client, item_id, location_id) == 8


def test_las_devoluciones_parciales_se_acumulan(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "3")

    admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "1"}], "location_id": location_id,
    })
    segunda = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "2"}], "location_id": location_id,
    })

    assert segunda.json()["status"] == "returned"
    assert _stock(admin_client, item_id, location_id) == 10


def test_devolver_una_linea_que_no_existe_es_422(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "1")

    respuesta = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 5, "quantity": "1"}], "location_id": location_id,
    })
    assert respuesta.status_code == 422


def test_devolver_sin_indicar_lineas_es_422(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "1")

    respuesta = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [], "location_id": location_id,
    })
    assert respuesta.status_code == 422


def test_no_se_devuelve_plata_sin_turno_abierto(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    turno_id = _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "1")
    admin_client.post(f"/shifts/{turno_id}/close", json={"monto_declarado": 0})

    respuesta = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "1"}], "location_id": location_id,
    })
    assert respuesta.status_code == 409


def test_devolver_a_cuenta_corriente_baja_la_deuda(admin_client):
    """Si la compra estaba fiada y todavía no se pagó, devolver no saca plata
    del cajón: descuenta lo que el cliente debe."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    turno_id = _abrir_turno(admin_client)
    cliente = admin_client.post("/customers", json={"display_name": "Vecina"}).json()["id"]
    sale_id = _venta(admin_client, item_id, location_id, "2",
                     pagos=[{"medio": "cuenta_corriente", "monto": "3000"}],
                     customer_id=cliente)

    admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "1"}],
        "location_id": location_id, "medio_pago": "cuenta_corriente",
    })

    assert Decimal(admin_client.get(f"/accounts/{cliente}").json()["saldo"]) == 1500
    # La caja no se movió.
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 0


def test_no_se_devuelve_a_cuenta_corriente_sin_cliente(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "1")

    respuesta = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "1"}],
        "location_id": location_id, "medio_pago": "cuenta_corriente",
    })
    assert respuesta.status_code == 422


def test_se_puede_devolver_por_otro_medio_del_que_se_cobro(admin_client):
    # Se cobró con tarjeta y se devuelve en efectivo: pasa en el mostrador.
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _con_stock(admin_client, item_id, location_id, "10")
    _abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, location_id, "1",
                     pagos=[{"medio": "tarjeta_debito", "monto": "1500"}])

    devuelta = admin_client.post(f"/sales/{sale_id}/returns", json={
        "lineas": [{"index": 0, "quantity": "1"}],
        "location_id": location_id, "medio_pago": "efectivo",
    })
    assert devuelta.status_code == 200, devuelta.text
    assert devuelta.json()["status"] == "returned"
