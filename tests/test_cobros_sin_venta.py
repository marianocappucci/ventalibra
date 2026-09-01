"""Los cobros que entraron y cuya venta quedó sin confirmar.

🔴 **El agujero que este producto declara en `services/mp_qr.py` y no vigilaba
nadie.** El orden acá es, a propósito, *"primero la plata, después la venta"* —
al revés que Contalibra, y por una buena razón: así no existe la ventana en la
que hay una venta registrada como cobrada que nadie pagó.

Pero el agujero se invierte: si el navegador se muere entre el poll y la
confirmación —se cierra la pestaña, se corta la luz, el cajero pasa a atender a
otro— **la plata entró y la venta no quedó registrada**.

La orden aprobada se guarda en `sale_mp_orders` justamente para eso. Lo que
faltaba es poder **encontrarla**: hasta hoy sólo se la consultaba por venta
(`orden_acreditada(conn, sale_id)`), así que la mitigación funcionaba únicamente
si alguien volvía a abrir ESE borrador. Si nadie lo abría, la plata estaba en
MercadoPago, no estaba en la caja, y no había forma de enterarse.
"""

from decimal import Decimal

from app.services import mp_qr

RUTA = "/sales/mp/cobros-sin-venta"


def _item(client, precio="1500.00"):
    """La forma sale de `tests/test_billing.py`, no de la memoria: el POST pide
    `name` y `unit_code`, y el precio es `default_sale_price`."""
    # La unidad se crea primero: `unit_code` es una FK contra `units` y sin
    # ella el POST devuelve 422 con "unidad desconocida".
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    r = client.post("/catalog/items", json={
        "name": "Gaseosa", "unit_code": "u",
        "default_sale_price": precio, "default_cost": "900.00"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _borrador(client, item_id):
    """Un borrador con un ítem: lo que el cajero tiene en pantalla cuando pone
    el monto en el QR."""
    draft = client.post("/sales", json={})
    assert draft.status_code in (200, 201), draft.text
    sale_id = draft.json()["id"]
    r = client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    assert r.status_code == 200, r.text
    return sale_id


def _orden_aprobada(conn, sale_id, payment_id="112233", monto="1500",
                    resuelta="2026-08-31 12:00:00", sufijo="a"):
    """Simula el cobro acreditado: la orden queda `approved` con su
    `payment_id`, que es exactamente lo que deja `estado_del_cobro` cuando
    MercadoPago dice que sí."""
    conn.execute(
        """INSERT INTO sale_mp_orders
             (sale_id, external_reference, amount, status, payment_id, resolved_at)
           VALUES (?,?,?,?,?,?)""",
        (sale_id, f"vl-{sale_id}-{sufijo}", monto, "approved", payment_id, resuelta),
    )
    conn.commit()


def test_un_cobro_acreditado_sin_venta_confirmada_aparece(admin_client):
    """🔴 El caso del defecto: la plata entró, el borrador quedó ahí, y nadie
    lo sabía."""
    conn = admin_client.app.state.conn
    sale_id = _borrador(admin_client, _item(admin_client))
    _orden_aprobada(conn, sale_id)

    r = admin_client.get(RUTA)
    assert r.status_code == 200, r.text
    filas = r.json()
    assert len(filas) == 1
    assert filas[0]["sale_id"] == sale_id
    assert filas[0]["payment_id"] == "112233"
    assert filas[0]["amount"] == 1500.0


def test_una_venta_confirmada_NO_aparece(admin_client):
    """🔑 **El control positivo, y la propiedad central de todo esto.**

    Si la lista devolviera todas las órdenes aprobadas, un cobro **bien
    registrado** figuraría como plata perdida y el cajero lo cobraría dos veces:
    exactamente el daño que esta pantalla viene a evitar, al revés.

    ⚠️ Este test estaba en el primer borrador del archivo y **se perdió** al
    reescribirlo para las fixtures reales del producto. Lo delató una mutación
    que sobrevivió: sacar `AND s.status = 'draft'` de la consulta no ponía nada
    en rojo.
    """
    conn = admin_client.app.state.conn
    sale_id = _borrador(admin_client, _item(admin_client))
    _orden_aprobada(conn, sale_id)
    # Con la orden ya acreditada figura en la lista...
    assert len(admin_client.get(RUTA).json()) == 1

    # Sin turno abierto, confirmar da 409: una venta fuera de turno sería plata
    # sin control de caja.
    admin_client.post("/shifts/open", json={"monto_inicial": 0})
    deposito = admin_client.post("/locations", json={"name": "Mostrador"})
    assert deposito.status_code == 200, deposito.text
    confirmada = admin_client.post(f"/sales/{sale_id}/confirm", json={
        "location_id": deposito.json()["id"], "medio_pago": "mercadopago"})
    assert confirmada.status_code == 200, confirmada.text

    # ...y al confirmarla deja de figurar.
    assert admin_client.get(RUTA).json() == []


def test_una_orden_pendiente_no_aparece(admin_client):
    """Una orden puesta en el QR que nadie escaneó **todavía no es plata que
    entró**. Listarla mandaría a buscar un cobro inexistente."""
    conn = admin_client.app.state.conn
    sale_id = _borrador(admin_client, _item(admin_client))
    conn.execute(
        """INSERT INTO sale_mp_orders (sale_id, external_reference, amount, status)
           VALUES (?,?,?,?)""",
        (sale_id, f"vl-{sale_id}-pend", "1500", "pending"),
    )
    conn.commit()

    assert admin_client.get(RUTA).json() == []


def test_una_orden_cancelada_tampoco(admin_client):
    conn = admin_client.app.state.conn
    sale_id = _borrador(admin_client, _item(admin_client))
    conn.execute(
        """INSERT INTO sale_mp_orders (sale_id, external_reference, amount, status)
           VALUES (?,?,?,?)""",
        (sale_id, f"vl-{sale_id}-canc", "1500", "cancelled"),
    )
    conn.commit()

    assert admin_client.get(RUTA).json() == []


def test_sin_cobros_huerfanos_devuelve_la_lista_vacia(admin_client):
    assert admin_client.get(RUTA).json() == []


def test_salen_del_mas_viejo_al_mas_nuevo(admin_client):
    """El más viejo es el que más urge: lleva más tiempo con la plata afuera de
    la caja.

    ⚠️ **Tres filas, y no dos.** Con dos insertadas al revés, `ORDER BY id DESC`
    daba el MISMO resultado que el correcto y la mutación sobrevivía: el dato de
    prueba hacía indistinguible el defecto. Acá los tres órdenes posibles —por
    id ascendente, por id descendente y por fecha— dan resultados distintos.
    """
    conn = admin_client.app.state.conn
    item = _item(admin_client)
    a, b, c = (_borrador(admin_client, item) for _ in range(3))
    _orden_aprobada(conn, a, payment_id="111", resuelta="2026-08-31 15:00:00", sufijo="a")
    _orden_aprobada(conn, b, payment_id="222", resuelta="2026-08-31 09:00:00", sufijo="b")
    _orden_aprobada(conn, c, payment_id="333", resuelta="2026-08-31 12:00:00", sufijo="c")

    filas = admin_client.get(RUTA).json()
    #   por fecha:      222, 333, 111   <- el correcto
    #   por id asc:     111, 222, 333
    #   por id desc:    333, 222, 111
    assert [f["payment_id"] for f in filas] == ["222", "333", "111"]


def test_la_consulta_del_servicio_devuelve_Decimal(admin_client):
    """El monto viaja como `Decimal` en el servicio: es plata, y sumarla en
    `float` para mostrar un total es de donde salen los centavos que no
    cierran."""
    conn = admin_client.app.state.conn
    sale_id = _borrador(admin_client, _item(admin_client))
    _orden_aprobada(conn, sale_id, monto="1500.5")

    filas = mp_qr.cobros_sin_venta(conn)
    assert len(filas) == 1
    assert isinstance(filas[0]["amount"], Decimal)
    assert filas[0]["amount"] == Decimal("1500.5")
