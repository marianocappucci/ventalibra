"""Fiado: vender a cuenta corriente, cobrar la deuda y ver el saldo.

La regla que ordenan todos estos tests: **fiar no es cobrar**. Una venta a
cuenta corriente no mueve plata, así que no puede aparecer en el arqueo del
turno; el movimiento de caja recién existe cuando el cliente viene a pagar.
Si eso se rompe, el cajero cierra cuadrando contra un total que no está en
el cajón.
"""
from decimal import Decimal


def _abrir_turno(client, monto_inicial=0):
    abierto = client.post("/shifts/open", json={"monto_inicial": monto_inicial})
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["turno"]["id"]


def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _make_location(client, name="Sucursal 1"):
    creada = client.post("/locations", json={"name": name})
    assert creada.status_code == 200, creada.text
    return creada.json()["id"]


def _make_cliente(client, nombre="Vecina del 12"):
    creado = client.post("/customers", json={"display_name": nombre})
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _venta_fiada(client, cliente_id, location_id, item_id, cantidad="2"):
    """Una venta cobrada íntegramente a cuenta corriente."""
    borrador = client.post("/sales", json={"customer_party_id": cliente_id})
    sale_id = borrador.json()["id"]
    client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": cantidad})
    confirmada = client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "cuenta_corriente"},
    )
    assert confirmada.status_code == 200, confirmada.text
    return confirmada.json()


def test_fiar_deja_la_deuda_en_la_cuenta_del_cliente(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    _venta_fiada(admin_client, cliente_id, location_id, item_id)

    cuenta = admin_client.get(f"/accounts/{cliente_id}")
    assert cuenta.status_code == 200, cuenta.text
    assert Decimal(cuenta.json()["saldo"]) == Decimal("3000")
    movimientos = cuenta.json()["movimientos"]
    assert len(movimientos) == 1
    assert movimientos[0]["tipo"] == "debito"


def test_lo_fiado_no_entra_al_arqueo_del_turno(admin_client):
    """El corazón del asunto: la plata no entró, así que la caja no la cuenta."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client, monto_inicial=5000)

    _venta_fiada(admin_client, cliente_id, location_id, item_id)

    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 0


def test_una_venta_en_efectivo_si_entra_al_arqueo(admin_client):
    """Contraprueba del test anterior: el mismo flujo pagando con plata sí
    mueve la caja, así que el cero de arriba es del fiado y no de que el
    resumen esté roto."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    turno_id = _abrir_turno(admin_client, monto_inicial=5000)

    borrador = admin_client.post("/sales", json={})
    sale_id = borrador.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "2"})
    admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo"},
    )

    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 3000


def test_no_se_le_puede_fiar_a_consumidor_final(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _abrir_turno(admin_client)

    borrador = admin_client.post("/sales", json={})  # sin cliente
    sale_id = borrador.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})

    respuesta = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "cuenta_corriente"},
    )
    assert respuesta.status_code == 422
    assert "consumidor final" in respuesta.json()["detail"]


def test_la_venta_rechazada_por_falta_de_cliente_no_se_confirma(admin_client):
    """El chequeo corre ANTES de confirmar: si fallara después, la venta
    quedaría cobrada sin que la deuda exista en ningún lado."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _abrir_turno(admin_client)

    borrador = admin_client.post("/sales", json={})
    sale_id = borrador.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "cuenta_corriente"},
    )

    assert admin_client.get(f"/sales/{sale_id}").json()["status"] == "draft"


def test_cobrar_baja_el_saldo_y_entra_a_la_caja(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, location_id, item_id)

    cobro = admin_client.post(
        f"/accounts/{cliente_id}/payments",
        json={"monto": "1000", "medio_pago": "efectivo"},
    )
    assert cobro.status_code == 200, cobro.text
    assert Decimal(cobro.json()["saldo"]) == Decimal("2000")

    # Cobrar deuda vieja SÍ es plata que entra: tiene que aparecer en el turno.
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 1000


def test_el_pago_queda_en_los_movimientos(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, location_id, item_id)

    admin_client.post(
        f"/accounts/{cliente_id}/payments",
        json={"monto": "1000", "medio_pago": "efectivo", "concepto": "Pago parcial"},
    )

    movimientos = admin_client.get(f"/accounts/{cliente_id}").json()["movimientos"]
    tipos = [m["tipo"] for m in movimientos]
    assert tipos == ["debito", "credito"]
    assert movimientos[1]["concepto"] == "Pago parcial"
    assert movimientos[1]["medio"] == "efectivo"


def test_pagar_de_mas_deja_saldo_a_favor(admin_client):
    # Pasa en el mostrador: el cliente redondea para arriba. Se acepta y
    # queda a favor en vez de rechazarse.
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, location_id, item_id)

    cobro = admin_client.post(
        f"/accounts/{cliente_id}/payments", json={"monto": "3500"},
    )
    assert Decimal(cobro.json()["saldo"]) == Decimal("-500")


def test_no_se_cobra_sin_turno_abierto(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, location_id, item_id)
    admin_client.post(f"/shifts/{turno_id}/close", json={"monto_declarado": 0})

    respuesta = admin_client.post(
        f"/accounts/{cliente_id}/payments", json={"monto": "1000"},
    )
    assert respuesta.status_code == 409


def test_un_monto_invalido_se_rechaza(admin_client):
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    assert admin_client.post(
        f"/accounts/{cliente_id}/payments", json={"monto": "0"},
    ).status_code == 422


def test_el_listado_de_deudores_los_devuelve_por_party_id(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    uno = _make_cliente(admin_client, "Vecina del 12")
    otro = _make_cliente(admin_client, "Kiosco de la esquina")
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, uno, location_id, item_id, cantidad="2")
    _venta_fiada(admin_client, otro, location_id, item_id, cantidad="1")

    deudores = admin_client.get("/accounts").json()
    por_id = {d["party_id"]: d for d in deudores}
    assert Decimal(por_id[uno]["saldo"]) == Decimal("3000")
    assert Decimal(por_id[otro]["saldo"]) == Decimal("1500")
    assert por_id[uno]["nombre"] == "Vecina del 12"


def test_un_cliente_sin_movimientos_no_figura_como_deudor(admin_client):
    _make_cliente(admin_client, "Cliente que paga al contado")
    assert admin_client.get("/accounts").json() == []


def test_dos_ventas_fiadas_se_acumulan(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    _venta_fiada(admin_client, cliente_id, location_id, item_id, cantidad="1")
    _venta_fiada(admin_client, cliente_id, location_id, item_id, cantidad="2")

    cuenta = admin_client.get(f"/accounts/{cliente_id}").json()
    assert Decimal(cuenta["saldo"]) == Decimal("4500")
    assert len(cuenta["movimientos"]) == 2


def test_cobro_mixto_con_una_parte_fiada(admin_client):
    """Paga una parte y queda debiendo el resto: a la caja entra sólo lo que
    se pagó, y a la cuenta corriente sólo lo que quedó debiendo."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client)

    borrador = admin_client.post("/sales", json={"customer_party_id": cliente_id})
    sale_id = borrador.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "2"})
    confirmada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={
            "location_id": location_id,
            "pagos": [
                {"medio": "efectivo", "monto": "1000"},
                {"medio": "cuenta_corriente", "monto": "2000"},
            ],
        },
    )
    assert confirmada.status_code == 200, confirmada.text

    assert Decimal(admin_client.get(f"/accounts/{cliente_id}").json()["saldo"]) == Decimal("2000")
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 1000


def test_la_cuenta_de_un_cliente_inexistente_es_404(admin_client):
    assert admin_client.get("/accounts/9999").status_code == 404


def test_se_le_puede_poner_cliente_a_una_venta_ya_empezada(admin_client):
    """En el mostrador el cajero se entera de que va fiado al cobrar, con las
    líneas ya cargadas: si hubiera que elegir el cliente antes de la primera,
    el fiado sería inusable."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    borrador = admin_client.post("/sales", json={})  # arranca sin cliente
    sale_id = borrador.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "2"})

    asignada = admin_client.patch(
        f"/sales/{sale_id}", json={"customer_party_id": cliente_id},
    )
    assert asignada.status_code == 200, asignada.text
    # El total no se toca al asignar el cliente.
    assert Decimal(asignada.json()["total"]) == Decimal("3000")

    confirmada = admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "cuenta_corriente"},
    )
    assert confirmada.status_code == 200, confirmada.text
    assert Decimal(admin_client.get(f"/accounts/{cliente_id}").json()["saldo"]) == Decimal("3000")


def test_no_se_le_cambia_el_cliente_a_una_venta_ya_cobrada(admin_client):
    # Mover la deuda de una venta cerrada a otra persona seria reescribir
    # quien debe, sin rastro.
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    borrador = admin_client.post("/sales", json={})
    sale_id = borrador.json()["id"]
    admin_client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    admin_client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo"},
    )

    respuesta = admin_client.patch(
        f"/sales/{sale_id}", json={"customer_party_id": cliente_id},
    )
    assert respuesta.status_code == 409
