"""El contrato del kit para la cuenta corriente: `/api/cuenta-corriente`.

Las pantallas del kit (`libra-ui/comercio/CuentaCorriente*`, las mismas que
montan Contalibra y Restolibra desde P9-M4) son las que ahora usa este
producto; el negocio sigue siendo el de `/accounts` +
`CuentaCorrienteService`, expuesto en las rutas fijas que el kit llama
(`app/routers/cuenta_corriente_api.py`). Lo que ordenan estos tests:

- **fiar no es cobrar** (mismo invariante que `test_cuenta_corriente.py`): el
  movimiento de caja recién existe cuando el pago entra;
- el cobro por el kit conserva las reglas de este producto: turno abierto y
  **caja del turno** de quien cobra;
- la baja de pago (admin) **anula** el movimiento de caja -- no lo borra, ver
  `CuentaCorrienteService.eliminar_pago` -- y con eso el arqueo vuelve a dar
  lo que hay en el cajón;
- los montos viajan como números: el kit compara `saldo > 0` y SUMA montos en
  el navegador, y un `Decimal`-string los concatenaría ("0" + "1500.0").
"""
from decimal import Decimal

from ventas_helpers import caja_default, hoy


def _abrir_turno(client, monto_inicial=0):
    abierto = client.post(
        "/shifts/open", json={"monto_inicial": monto_inicial, "caja_id": caja_default(client)}
    )
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["turno"]["id"]


def _cerrar_turno(client, turno_id):
    respuesta = client.post(f"/shifts/{turno_id}/close", json={"monto_declarado": 0})
    assert respuesta.status_code == 200, respuesta.text


def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _make_cliente(client, nombre="Vecina del 12"):
    creado = client.post("/api/clientes", json={"name": nombre})
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _venta_fiada(client, cliente_id, item_id, cantidad="2", precio="1500.00"):
    """Una venta cobrada íntegramente a cuenta corriente: ese pago ES la deuda."""
    total = float(cantidad) * float(precio)
    creada = client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": float(cantidad), "precio": float(precio),
                   "producto_id": item_id}],
        "pagos": [{"medio": "cuenta_corriente", "monto": total}],
        "cliente_id": cliente_id,
    })
    assert creada.status_code == 200, creada.text
    return creada.json()


def _deudor_con_pago(client, monto_pago="1000"):
    """Un cliente con venta fiada (3000) y un pago registrado por el kit.

    Devuelve `(cliente_id, pago_id, turno_id)`."""
    item_id = _make_item(client)
    cliente_id = _make_cliente(client)
    turno_id = _abrir_turno(client)
    _venta_fiada(client, cliente_id, item_id)

    cobro = client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"monto": float(monto_pago), "fecha": hoy(), "medio_pago": "efectivo"},
    )
    assert cobro.status_code == 200, cobro.text
    pago_id = next(
        m["cc_pago_id"] for m in cobro.json()["movimientos"] if m["cc_pago_id"] is not None
    )
    return cliente_id, pago_id, turno_id


# ── El listado ───────────────────────────────────────────────────────────────

def test_el_listado_del_kit_trae_clientes_y_total_deuda(admin_client):
    item_id = _make_item(admin_client)
    uno = _make_cliente(admin_client, "Vecina del 12")
    otro = _make_cliente(admin_client, "Kiosco de la esquina")
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, uno, item_id, cantidad="2")
    _venta_fiada(admin_client, otro, item_id, cantidad="1")

    # Uno salda una parte, como en la vida real.
    admin_client.post(
        f"/api/cuenta-corriente/{uno}/pagar",
        json={"monto": 1000.0, "fecha": hoy(), "medio_pago": "efectivo"},
    )

    listado = admin_client.get("/api/cuenta-corriente")
    assert listado.status_code == 200, listado.text
    por_id = {c["id"]: c for c in listado.json()["clientes"]}
    assert por_id[uno]["name"] == "Vecina del 12"
    assert por_id[uno]["saldo"] == 2000.0
    assert por_id[otro]["saldo"] == 1500.0
    assert listado.json()["total_deuda"] == 3500.0
    # 🔴 Números, no `Decimal`-string: el kit suma los saldos en el navegador.
    assert isinstance(por_id[uno]["saldo"], float)
    assert isinstance(listado.json()["total_deuda"], float)


def test_el_listado_del_kit_no_muestra_al_que_no_debe(admin_client):
    _make_item(admin_client)
    _make_cliente(admin_client, "Cliente que paga al contado")
    _abrir_turno(admin_client)

    assert admin_client.get("/api/cuenta-corriente").json()["clientes"] == []


# ── El detalle ───────────────────────────────────────────────────────────────

def test_el_detalle_del_kit_trae_cliente_movimientos_y_saldo(admin_client):
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client, "Vecina del 12")
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)

    detalle = admin_client.get(f"/api/cuenta-corriente/{cliente_id}")
    assert detalle.status_code == 200, detalle.text
    cuerpo = detalle.json()
    assert cuerpo["cliente"]["id"] == cliente_id
    assert cuerpo["cliente"]["name"] == "Vecina del 12"
    assert cuerpo["saldo"] == 3000.0
    assert isinstance(cuerpo["saldo"], float)
    # Movimiento con el contrato que el kit muestra (MovimientoCC): fecha,
    # tipo, concepto, monto, referencia, medio, cc_pago_id, usuario_nombre,
    # venta_id y factura_id.
    movimiento = cuerpo["movimientos"][0]
    assert movimiento["tipo"] == "debito"
    assert movimiento["monto"] == 3000.0
    assert movimiento["concepto"].startswith("Venta #")
    assert movimiento["venta_id"] is not None
    assert movimiento["factura_id"] is None
    assert movimiento["cc_pago_id"] is None
    for clave in ("fecha", "referencia", "medio", "usuario_nombre"):
        assert clave in movimiento


def test_el_detalle_de_un_cliente_inexistente_es_404(admin_client):
    assert admin_client.get("/api/cuenta-corriente/9999").status_code == 404


# ── El pago ──────────────────────────────────────────────────────────────────

def test_pagar_por_el_kit_baja_el_saldo_entra_a_la_caja_y_emite_recibo(admin_client):
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)

    cobro = admin_client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"monto": 1000.0, "fecha": hoy(), "medio_pago": "efectivo",
              "concepto": "Pago parcial", "referencia": "TRF-99"},
    )
    assert cobro.status_code == 200, cobro.text
    cuerpo = cobro.json()
    assert cuerpo["saldo"] == 2000.0
    # El recibo emite solo (ver test_recibos.py: si esto vuelve None, un
    # cableado roto pasa desapercibido porque el cobro igual es válido).
    assert cuerpo["recibo_id"] is not None
    assert [m["tipo"] for m in cuerpo["movimientos"]] == ["debito", "credito"]
    assert cuerpo["movimientos"][1]["concepto"] == "Pago parcial"
    assert cuerpo["movimientos"][1]["referencia"] == "TRF-99"

    # Cobrar deuda vieja SÍ es plata que entra, en el turno de quien cobró.
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 1000


def test_pagar_con_la_caja_del_turno_en_el_body_es_200(admin_client):
    """El kit manda `caja_id` (la del selector); si es la del turno, pasa."""
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)

    caja_del_turno = caja_default(admin_client)
    cobro = admin_client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"monto": 500.0, "fecha": hoy(), "medio_pago": "efectivo",
              "caja_id": caja_del_turno},
    )
    assert cobro.status_code == 200, cobro.text


def test_pagar_con_otra_caja_se_rechaza(admin_client):
    """El selector del kit en este producto ofrece una sola caja -- la del
    turno. Si `caja_id` viene con otra, no hay que aceptarlo en silencio: el
    pago quedaría anotado en una caja cuyo arqueo no lo cuenta."""
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)

    respuesta = admin_client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"monto": 1000.0, "fecha": hoy(), "medio_pago": "efectivo",
              "caja_id": caja_default(admin_client) + 1000},
    )
    assert respuesta.status_code == 422, respuesta.text
    assert "caja del turno" in respuesta.json()["detail"].lower()


def test_pagar_sin_turno_abierto_da_409(admin_client):
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)
    _cerrar_turno(admin_client, turno_id)

    respuesta = admin_client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"monto": 1000.0, "fecha": hoy(), "medio_pago": "efectivo"},
    )
    assert respuesta.status_code == 409


def test_la_cuenta_corriente_no_es_un_medio_de_cobro(admin_client):
    """Mismo criterio que `CobranzaIn`: cobrar una deuda "con cuenta
    corriente" registraría un cobro que no cobra nada."""
    _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    respuesta = admin_client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"monto": 1000.0, "fecha": hoy(), "medio_pago": "cuenta_corriente"},
    )
    assert respuesta.status_code == 422


def test_un_monto_invalido_se_rechaza(admin_client):
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    respuesta = admin_client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"monto": 0, "fecha": hoy(), "medio_pago": "efectivo"},
    )
    assert respuesta.status_code == 422


# ── El selector de caja ──────────────────────────────────────────────────────

def test_el_selector_de_cajas_ofrece_la_caja_del_turno(admin_client):
    """En Contalibra el selector ofrece todas las cajas; acá el ingreso SIEMPRE
    cae en la caja del turno de quien cobra, así que ofrecer las demás sería
    ofrecer algo que el backend no honra."""
    _make_item(admin_client)
    _abrir_turno(admin_client)

    cajas = admin_client.get("/api/cuenta-corriente/cajas")
    assert cajas.status_code == 200, cajas.text
    assert [c["id"] for c in cajas.json()] == [caja_default(admin_client)]


def test_el_selector_de_cajas_sin_turno_viene_vacio(admin_client):
    _make_item(admin_client)
    turno_id = _abrir_turno(admin_client)
    _cerrar_turno(admin_client, turno_id)

    assert admin_client.get("/api/cuenta-corriente/cajas").json() == []


# ── La baja del pago ─────────────────────────────────────────────────────────

def test_la_baja_del_pago_devuelve_la_plata_y_el_saldo(admin_client):
    cliente_id, pago_id, turno_id = _deudor_con_pago(admin_client)
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 1000

    baja = admin_client.delete(f"/api/cuenta-corriente/pagos/{pago_id}")
    assert baja.status_code == 200, baja.text

    # El saldo vuelve (el pago ya no existe) y el arqueo deja de contar la
    # plata -- el movimiento queda ANULADO en la fila, no borrado.
    cuenta = admin_client.get(f"/api/cuenta-corriente/{cliente_id}")
    assert cuenta.json()["saldo"] == 3000.0
    assert "credito" not in [m["tipo"] for m in cuenta.json()["movimientos"]]
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 0


def test_el_recibo_del_pago_bajado_no_se_puede_reemitir(admin_client):
    """Borrar el pago anula su recibo; si el pago ya no está, la ruta
    idempotente del kit contesta 404 en vez de inventar un comprobante."""
    cliente_id, pago_id, _turno_id = _deudor_con_pago(admin_client)
    emitido = admin_client.post(f"/api/recibos/cobranza/{pago_id}")
    assert emitido.status_code == 200, emitido.text

    admin_client.delete(f"/api/cuenta-corriente/pagos/{pago_id}")
    assert admin_client.post(f"/api/recibos/cobranza/{pago_id}").status_code == 404


def test_el_pdf_del_recibo_sale_por_la_ruta_del_kit(admin_client):
    """El kit abre el PDF por URL del navegador (con la cookie), igual que
    hacía la pantalla propia con `/accounts/receipts/.../pdf`."""
    import io

    from pypdf import PdfReader

    cliente_id, pago_id, _turno_id = _deudor_con_pago(admin_client)
    recibo_id = admin_client.post(f"/api/recibos/cobranza/{pago_id}").json()["id"]

    pdf = admin_client.get(f"/api/recibos/{recibo_id}/pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    texto = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Vecina del 12" in texto


def test_el_recibo_del_kit_es_el_mismo_que_el_de_la_ruta_vieja(admin_client):
    """`POST /api/recibos/cobranza/{id}` y `POST /accounts/receipts/{id}` son
    la misma operación idempotente: dos llamadas, un solo recibo."""
    cliente_id, pago_id, _turno_id = _deudor_con_pago(admin_client)

    por_kit = admin_client.post(f"/api/recibos/cobranza/{pago_id}")
    por_ruta_vieja = admin_client.post(f"/accounts/receipts/{pago_id}")
    assert por_kit.status_code == 200 and por_ruta_vieja.status_code == 200
    assert por_kit.json()["id"] == por_ruta_vieja.json()["id"]


def test_la_baja_de_pago_es_solo_admin(admin_client, staff_client):
    cliente_id, pago_id, _turno_id = _deudor_con_pago(admin_client)

    assert staff_client.delete(
        f"/api/cuenta-corriente/pagos/{pago_id}").status_code == 403
    # El admin de la misma instancia sí puede: el pago se borra, el movimiento
    # queda anulado y el saldo vuelve al valor de antes del pago.
    assert admin_client.delete(
        f"/api/cuenta-corriente/pagos/{pago_id}").status_code == 200
    assert admin_client.get(f"/api/cuenta-corriente/{cliente_id}").json()["saldo"] == 3000.0