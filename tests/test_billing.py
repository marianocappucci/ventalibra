from libracore.db import caja as db_caja


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


def _make_location(client, name="Sucursal 1"):
    created = client.post("/locations", json={"name": name})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _confirmed_sale(client, item_id, location_id, quantity="1", **confirm_extra):
    _abrir_turno(client)
    draft = client.post("/sales", json={})
    sale_id = draft.json()["id"]
    client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": quantity})
    return client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo", **confirm_extra},
    )


def test_get_arca_config_defaults_to_none(admin_client):
    response = admin_client.get("/config/arca")
    assert response.status_code == 200
    assert response.json() is None


def test_set_and_get_arca_config(admin_client):
    """🔴 La fila se crea con `venta`, que es el slug con el que
    `services/billing.py` lee la configuracion de facturacion.

    Con `default` --el valor al que caia el router del motor antes de que el
    producto pudiera declarar el suyo-- el PUT contesta 200 y la pantalla dice
    "Guardado", pero la facturacion no lee esa fila NUNCA: se descubre al emitir
    el primer comprobante. Ver `empresa_por_defecto` en LibraCore v1.63.0.

    El cuerpo ya no lleva los paths: el certificado se sube, y el path lo pone
    el servidor. Ver `test_el_certificado_se_sube`.
    """
    created = admin_client.put("/config/arca", json={
        "cuit": "30-12345678-9", "punto_venta": 1,
    })
    assert created.status_code == 200, created.text
    assert created.json()["empresa"] == "venta"

    fetched = admin_client.get("/config/arca")
    assert fetched.json()["cuit"] == "30-12345678-9"


def test_el_certificado_se_sube_y_se_valida_antes_de_escribirlo(admin_client):
    """Subir el `.csr` --el pedido-- en vez del `.crt` que ARCA devuelve es el
    error habitual, y antes se aceptaba: el router propio escribia el path que
    le mandaran sin mirar nada, y fallaba recien al emitir."""
    r = admin_client.post(
        "/config/arca/certificado",
        files={"archivo": ("pedido.pem", b"-----BEGIN CERTIFICATE REQUEST-----", "text/plain")},
    )
    assert r.status_code == 422
    assert "certificado" in r.json()["detail"].lower()


def test_el_estado_dice_si_la_instancia_puede_facturar(admin_client):
    """🔑 Trae el vencimiento del certificado, que es el dato que evita la falla
    silenciosa: duran dos anos y el dia que vencen la facturacion deja de andar
    sin que nadie haya tocado nada."""
    r = admin_client.get("/config/arca/estado")
    assert r.status_code == 200
    assert r.json()["configurado"] is False


def test_confirm_without_invoice_flag_does_not_bill(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    confirmed = _confirmed_sale(admin_client, item_id, location_id)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["factura"] is None


def test_confirm_with_invoice_and_no_customer_bills_consumidor_final(admin_client):
    item_id = _make_item(admin_client, price="1000.00")
    location_id = _make_location(admin_client)
    confirmed = _confirmed_sale(admin_client, item_id, location_id, invoice=True)
    assert confirmed.status_code == 200, confirmed.text
    factura = confirmed.json()["factura"]
    assert factura is not None
    assert factura["cliente_razon"] == "Consumidor Final"
    assert factura["tipo"] == 6  # factura B
    assert factura["cae"] is not None  # mock de dev, ver arca_facturacion.get_next_numero_with_arca


def test_confirm_with_invoice_and_responsable_inscripto_customer_bills_type_a(admin_client):
    customer = admin_client.post("/customers", json={
        "display_name": "Empresa SA", "party_type": "organization",
        "cuit": "30-99999999-1", "condicion_iva": "Responsable Inscripto",
    })
    customer_id = customer.json()["id"]

    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _abrir_turno(admin_client)
    draft = admin_client.post("/sales", json={"customer_party_id": customer_id})
    sale_id = draft.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    confirmed = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "tarjeta", "invoice": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    factura = confirmed.json()["factura"]
    assert factura["tipo"] == 1  # factura A
    assert factura["cliente_cuit"] == "30-99999999-1"


def test_confirming_a_sale_always_records_a_caja_movement(admin_client):
    item_id = _make_item(admin_client, price="500.00")
    location_id = _make_location(admin_client)

    before = len(db_caja.get_caja_movimientos())
    confirmed = _confirmed_sale(admin_client, item_id, location_id)
    assert confirmed.status_code == 200, confirmed.text
    sale_number = confirmed.json()["number"]

    movimientos = db_caja.get_caja_movimientos()
    assert len(movimientos) == before + 1
    assert movimientos[0]["concepto"] == f"Venta {sale_number}"
    assert movimientos[0]["factura_id"] is None
    assert float(movimientos[0]["monto"]) == 500.0
