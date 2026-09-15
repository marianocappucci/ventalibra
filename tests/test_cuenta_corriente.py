"""Fiado: vender a cuenta corriente, cobrar la deuda y ver el saldo.

Portado a la capa ERP de LibraCommerce (F3, ADR-025): la venta se registra
completa en una sola llamada (`POST /api/ventas`, D1) en vez de
borrador+`PATCH`+`confirm`. `/accounts` no cambió -- ya leía por `party_id`
vía `CuentaCorrienteService` (D3, cruce por `external_ref`).

La regla que ordenan todos estos tests: **fiar no es cobrar**. Una venta a
cuenta corriente no mueve plata, así que no puede aparecer en el arqueo del
turno; el movimiento de caja recién existe cuando el cliente viene a pagar.
Si eso se rompe, el cajero cierra cuadrando contra un total que no está en
el cajón.
"""
from decimal import Decimal

from ventas_helpers import hoy


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


def _make_cliente(client, nombre="Vecina del 12"):
    creado = client.post("/customers", json={"display_name": nombre})
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _registrar_venta(client, item_id, *, cliente_id=None, precio="1500.00", cantidad="2",
                     pagos=None):
    """Registra la venta completa en una sola llamada (D1)."""
    total = float(cantidad) * float(precio)
    payload = {
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": float(cantidad), "precio": float(precio),
                  "producto_id": item_id}],
        "pagos": pagos or [{"medio": "efectivo", "monto": total}],
    }
    if cliente_id is not None:
        payload["cliente_id"] = cliente_id
    creada = client.post("/api/ventas", json=payload)
    assert creada.status_code == 200, creada.text
    return creada.json()


def _venta_fiada(client, cliente_id, item_id, cantidad="2", precio="1500.00"):
    """Una venta cobrada íntegramente a cuenta corriente."""
    total = float(cantidad) * float(precio)
    return _registrar_venta(
        client, item_id, cliente_id=cliente_id, precio=precio, cantidad=cantidad,
        pagos=[{"medio": "cuenta_corriente", "monto": total}],
    )


def test_fiar_deja_la_deuda_en_la_cuenta_del_cliente(admin_client):
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    _venta_fiada(admin_client, cliente_id, item_id)

    cuenta = admin_client.get(f"/accounts/{cliente_id}")
    assert cuenta.status_code == 200, cuenta.text
    assert Decimal(str(cuenta.json()["saldo"])) == Decimal("3000")
    movimientos = cuenta.json()["movimientos"]
    assert len(movimientos) == 1
    assert movimientos[0]["tipo"] == "debito"


def test_lo_fiado_no_entra_al_arqueo_del_turno(admin_client):
    """El corazón del asunto: la plata no entró, así que la caja no la cuenta."""
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client, monto_inicial=5000)

    _venta_fiada(admin_client, cliente_id, item_id)

    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 0


def test_una_venta_en_efectivo_si_entra_al_arqueo(admin_client):
    """Contraprueba del test anterior: el mismo flujo pagando con plata sí
    mueve la caja, así que el cero de arriba es del fiado y no de que el
    resumen esté roto."""
    item_id = _make_item(admin_client)
    turno_id = _abrir_turno(admin_client, monto_inicial=5000)

    _registrar_venta(admin_client, item_id, cantidad="2")

    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 3000


def test_no_se_le_puede_fiar_a_consumidor_final(admin_client):
    """Cerrado en libracommerce v0.16.2: `OpcionesVentas.exigir_cliente_para_
    fiar` (prendida en `app/main.py`) rechaza con 422 un pago 'cuenta_
    corriente' sin `cliente_id`, antes de escribir nada -- el mensaje del
    motor no dice "consumidor final" (eso era del modelo viejo, retirado),
    dice que no se puede fiar sin cliente."""
    item_id = _make_item(admin_client)
    _abrir_turno(admin_client)

    respuesta = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 1, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "cuenta_corriente", "monto": 1500.0}],
    })
    assert respuesta.status_code == 422, respuesta.text
    assert "sin cliente" in respuesta.json()["detail"].lower()


# 🔴 **Retirado, invariante ya no aplica**: `test_la_venta_rechazada_por_falta_de_cliente_no_se_
# confirma` (del modelo viejo) afirmaba que el chequeo de "no se le puede fiar a consumidor
# final" corría ANTES de confirmar, dejando la venta en `draft` si fallaba -- para que no
# quedara cobrada sin que la deuda existiera en ningún lado. D1 borró el concepto de "borrador
# que puede fallar al confirmar": `POST /api/ventas` es atómico, una sola llamada que o registra
# la venta completa o no registra nada (ver `libracommerce.erp.ventas.crear_venta_directa`, que
# hace rollback de la transacción entera ante cualquier excepción). No hay un estado intermedio
# que verificar aparte del que ya cubre el test de arriba.


def test_cobrar_baja_el_saldo_y_entra_a_la_caja(admin_client):
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)

    cobro = admin_client.post(
        f"/accounts/{cliente_id}/payments",
        json={"monto": "1000", "medio_pago": "efectivo"},
    )
    assert cobro.status_code == 200, cobro.text
    assert Decimal(str(cobro.json()["saldo"])) == Decimal("2000")

    # Cobrar deuda vieja SÍ es plata que entra: tiene que aparecer en el turno.
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 1000


def test_el_pago_queda_en_los_movimientos(admin_client):
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)

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
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)

    cobro = admin_client.post(
        f"/accounts/{cliente_id}/payments", json={"monto": "3500"},
    )
    assert Decimal(str(cobro.json()["saldo"])) == Decimal("-500")


def test_no_se_cobra_sin_turno_abierto(admin_client):
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client)
    _venta_fiada(admin_client, cliente_id, item_id)
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
    """🔴 Gap cerrado en F3 (2026-09-14, ADR-025): `libracommerce.erp.ventas.
    registrar_venta` NUNCA llama a `hooks.cliente_cc_de` -- ese gancho sólo lo
    llaman `anular_venta`/`devolver_items` (las reversiones). No se parchea el
    motor (compartido por seis productos): se adelanta la creación de la fila
    `clients` al alta del cliente (`app/services/customers.py::CustomerService.
    create`, que ahora la crea de una) en vez de esperar a que alguien pida su
    cuenta puntual -- `_make_cliente()` de este archivo pega justo ahí."""
    item_id = _make_item(admin_client)
    uno = _make_cliente(admin_client, "Vecina del 12")
    otro = _make_cliente(admin_client, "Kiosco de la esquina")
    _abrir_turno(admin_client)
    _venta_fiada(admin_client, uno, item_id, cantidad="2")
    _venta_fiada(admin_client, otro, item_id, cantidad="1")

    deudores = admin_client.get("/accounts").json()
    por_id = {d["party_id"]: d for d in deudores}
    assert Decimal(str(por_id[uno]["saldo"])) == Decimal("3000")
    assert Decimal(str(por_id[otro]["saldo"])) == Decimal("1500")
    assert por_id[uno]["nombre"] == "Vecina del 12"


def test_un_cliente_sin_movimientos_no_figura_como_deudor(admin_client):
    _make_cliente(admin_client, "Cliente que paga al contado")
    assert admin_client.get("/accounts").json() == []


def test_un_cliente_sin_external_ref_no_rompe_el_listado(admin_client):
    """`deudores()` traduce cada fila de `clients` a un `party_id` por
    `external_ref = 'party-<id>'` (`app/services/cuenta_corriente.py::
    _party_id_de`); un cliente sin esa forma "no debería existir en esta
    base, pero si aparece no se lo muestra en vez de romper la pantalla"
    (ver el docstring de `deudores()`) -- no viene de VentaLibra."""
    conn = admin_client.app.state.conn
    cliente_id = conn.execute(
        "INSERT INTO clients (name, cuit_dni) VALUES ('Cliente sin party', '')"
    ).lastrowid
    conn.execute(
        "INSERT INTO cc_debitos (cliente_id, monto, fecha, concepto) VALUES (?, 500, '2026-09-14', 'x')",
        (cliente_id,),
    )
    conn.commit()

    assert admin_client.get("/accounts").json() == []


def test_un_external_ref_mal_formado_no_rompe_el_listado(admin_client):
    """Mismo caso, con un `external_ref` que empieza como se espera pero
    cuyo sufijo no es un id numérico -- dato corrupto, no un caso de uso."""
    conn = admin_client.app.state.conn
    cliente_id = conn.execute(
        "INSERT INTO clients (name, cuit_dni, external_ref) "
        "VALUES ('Cliente con external_ref roto', '', 'party-abc')"
    ).lastrowid
    conn.execute(
        "INSERT INTO cc_debitos (cliente_id, monto, fecha, concepto) VALUES (?, 500, '2026-09-14', 'x')",
        (cliente_id,),
    )
    conn.commit()

    assert admin_client.get("/accounts").json() == []


def test_dos_ventas_fiadas_se_acumulan(admin_client):
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    _abrir_turno(admin_client)

    _venta_fiada(admin_client, cliente_id, item_id, cantidad="1")
    _venta_fiada(admin_client, cliente_id, item_id, cantidad="2")

    cuenta = admin_client.get(f"/accounts/{cliente_id}").json()
    assert Decimal(str(cuenta["saldo"])) == Decimal("4500")
    assert len(cuenta["movimientos"]) == 2


def test_cobro_mixto_con_una_parte_fiada(admin_client):
    """Paga una parte y queda debiendo el resto: a la caja entra sólo lo que
    se pagó, y a la cuenta corriente sólo lo que quedó debiendo."""
    item_id = _make_item(admin_client)
    cliente_id = _make_cliente(admin_client)
    turno_id = _abrir_turno(admin_client)

    confirmada = _registrar_venta(
        admin_client, item_id, cliente_id=cliente_id, cantidad="2",
        pagos=[
            {"medio": "efectivo", "monto": 1000},
            {"medio": "cuenta_corriente", "monto": 2000},
        ],
    )
    assert confirmada["estado"] == "cobrada"

    assert Decimal(str(admin_client.get(f"/accounts/{cliente_id}").json()["saldo"])) == Decimal("2000")
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 1000


def test_la_cuenta_de_un_cliente_inexistente_es_404(admin_client):
    assert admin_client.get("/accounts/9999").status_code == 404


# 🔴 **Retirados, invariante ya no aplica**: `test_se_le_puede_poner_cliente_a_una_venta_ya_
# empezada` y `test_no_se_le_cambia_el_cliente_a_una_venta_ya_cobrada` (del modelo viejo)
# probaban `PATCH /sales/{id}` -- que hoy contesta 410 (ver `app/routers/sales.py`): "asignar
# cliente a una venta ahora se hace al registrarla en `POST /api/ventas` (D1: el POS arma la
# venta en el navegador y la registra en una sola llamada, ya con el cliente elegido)". La razón
# de mostrador que motivaba el `PATCH` -- el cajero se entera de que va fiado recién al cobrar,
# con las líneas ya cargadas -- sigue siendo válida, pero ahora es un problema del armado en el
# NAVEGADOR (F4, `Pos.tsx`), no de la API: no hay más "venta ya empezada" del lado del servidor
# a la que ponerle o no poder cambiarle el cliente.
