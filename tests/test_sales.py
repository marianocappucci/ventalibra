"""El punto de venta: registrar una venta, cobrar y el turno de caja.

Portado a la capa ERP de LibraCommerce (F3, ADR-025): `POST /api/ventas`
registra la venta completa en una sola llamada (D1) -- ya no hay un borrador
que se llena de a una línea (`POST /sales` + `/items` + `/confirm`, retirados
a 410, ver `app/routers/sales.py`). Varios invariantes del modelo viejo eran
del borrador incremental en sí (agregar, corregir, quitar una línea antes de
cobrar) y quedan retirados con su justificación al lado; los de cobro, turno y
arqueo se portan porque no dependían de CÓMO se armó la venta, sólo de qué
quedó cobrado.
"""
import pytest
from ventas_helpers import abrir_turno, con_stock, crear_item, deposito_default, hoy, registrar_venta, stock


def _make_item(client, name="Fideos 500g", price="1500.00"):
    return crear_item(client, name=name, price=price)


def test_sales_ya_no_existe(admin_client):
    """F4 (2026-09-15, ADR-025): `/sales` se retiró entero (`app/routers/
    sales.py` no existe más) -- lo que hasta F3 contestaba 410 apuntando a
    `/api/ventas` ahora no tiene router que lo sirva, así que cae en el
    catch-all de la SPA en producción (`app/spa.py`, sólo se monta con un
    frontend buildeado) o, en la suite -- sin ese mount --, en un 404 liso de
    FastAPI. Cualquiera de las dos formas confirma lo mismo: no hay ningún
    endpoint bajo `/sales`, ni de lectura ni de escritura."""
    sid = 1
    retiradas = [
        ("get", "/sales", None),
        ("post", "/sales", {}),
        ("get", f"/sales/{sid}", None),
        ("get", f"/sales/{sid}/ticket", None),
        ("patch", f"/sales/{sid}", {}),
        ("post", f"/sales/{sid}/items", {}),
        ("delete", f"/sales/{sid}/items/0", None),
        ("patch", f"/sales/{sid}/items/0", {}),
        ("post", f"/sales/{sid}/confirm", {}),
        ("post", f"/sales/{sid}/cancel", {}),
        ("post", f"/sales/{sid}/returns", {}),
        ("post", f"/sales/{sid}/mp-qr", {}),
        ("delete", f"/sales/{sid}/mp-qr", None),
        ("get", "/sales/mp/estado", None),
        ("get", "/sales/mp/cobros-sin-venta", None),
    ]
    for metodo, ruta, cuerpo in retiradas:
        llamar = getattr(admin_client, metodo)
        respuesta = llamar(ruta, json=cuerpo) if cuerpo is not None else llamar(ruta)
        assert respuesta.status_code == 404, f"{metodo.upper()} {ruta}: {respuesta.text}"


def test_full_pos_flow_confirms_sale_and_decrements_stock(admin_client):
    item_id = _make_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "20")
    abrir_turno(admin_client)

    venta = registrar_venta(admin_client, item_id, precio="1500.00", cantidad="3")
    assert venta["estado"] == "cobrada"
    assert float(venta["total"]) == 4500.0
    assert venta["factura_id"] is None
    # D5: se mantiene el prefijo de siempre (`app/ganchos.py::numerador`).
    assert venta["numero"].startswith("POS-")

    assert stock(admin_client, item_id, location_id) == 17


def test_registrar_venta_con_cliente_completa_su_nombre(admin_client):
    """🔴 `OpcionesVentas.nombre_de_cliente` por default busca `cliente_id` en
    `clients` (`libracore.db.clients.get_client`): acá ese id es un
    `party_id` de LibraCommerce (D3, ADR-025), no un `clients.id`, así que sin
    `app/ganchos.py::nombre_de_cliente` (montado en `app/main.py`) la venta
    quedaba con `cliente_nombre` vacío aunque sí tuviera cliente."""
    item_id = _make_item(admin_client)
    abrir_turno(admin_client)
    cliente = admin_client.post("/customers", json={"display_name": "Vecina del 12"})
    assert cliente.status_code == 200, cliente.text

    venta = registrar_venta(admin_client, item_id, cliente_id=cliente.json()["id"])
    assert venta["cliente_nombre"] == "Vecina del 12"


def test_confirm_without_items_fails(admin_client):
    abrir_turno(admin_client)
    respuesta = admin_client.post("/api/ventas", json={
        "fecha": hoy(), "items": [],
        "pagos": [{"medio": "efectivo", "monto": 0}],
    })
    assert respuesta.status_code == 422


# 🔴 **Retirado, invariante de borrador incremental**:
# `test_cannot_add_item_after_confirm` probaba que `POST /sales/{id}/items` fallaba
# sobre una venta ya confirmada. D1 borró el concepto: no hay más "agregar una línea" como
# operación de la API -- toda la venta (líneas, pagos, cliente) se manda junta en
# `POST /api/ventas`, que es atómica. No hay un estado "confirmada pero todavía se le puede
# agregar algo" que verificar.


def test_add_item_with_unknown_item_id_fails(admin_client):
    """Cerrado en libracommerce v0.16.2: un `producto_id` que no existe en el
    catálogo levanta `ProductoInexistente` -> 422, ANTES del catch-all que
    daba 409 ("conflicto con otra venta simultánea") -- ese sí seguía siendo
    correcto para un choque de verdad (`sales.number`), pero para un producto
    inexistente reintentar daba el mismo 409 para siempre."""
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id=999999, cantidad="1", precio="10.00", esperar=422)
    assert "999999" in venta["detail"]


def test_get_unknown_sale_404(admin_client):
    assert admin_client.get("/api/ventas/999").status_code == 404


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
    location_id = deposito_default(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item["id"], "location_id": location_id, "quantity_delta": "10",
              "variant_id": variant_m["id"]},
    )
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item["id"], "location_id": location_id, "quantity_delta": "5",
              "variant_id": variant_l["id"]},
    )
    abrir_turno(admin_client)

    venta = registrar_venta(admin_client, items=[
        {"nombre": "Remera M", "qty": 2, "precio": 5000.0, "producto_id": item["id"],
         "variante_id": variant_m["id"]},
    ])
    assert venta["items"][0]["variante_id"] == variant_m["id"]

    stock_m = admin_client.get(f"/stock/{item['id']}", params={"location_id": location_id, "variant_id": variant_m["id"]})
    stock_l = admin_client.get(f"/stock/{item['id']}", params={"location_id": location_id, "variant_id": variant_l["id"]})
    assert float(stock_m.json()["quantity"]) == 8.0
    assert float(stock_l.json()["quantity"]) == 5.0


# 🔴 **Retirado, invariante de borrador incremental**: `test_add_item_with_unknown_variant_fails`
# probaba el 422 de `POST /sales/{id}/items` contra un `variant_id` inexistente -- mismo
# mecanismo que `test_add_item_with_unknown_item_id_fails` de arriba (D1: sin lookup contra el
# catálogo al registrar). No se repite una segunda vez el mismo cambio de invariante.

# 🔴 **Retirados, invariante ya no aplica**: `test_add_item_uses_resolved_price_list_over_default`
# y `test_add_item_falls_back_to_default_sale_price_without_price_list_match` probaban que
# `POST /sales/{id}/items` resolvía el precio vigente de una lista de precios en el SERVIDOR
# cuando no se mandaba `unit_price`. `POST /api/ventas` no tiene ese camino: el payload exige
# `precio` por línea (D1, el navegador arma la venta ya con el precio resuelto -- la pantalla de
# POS con listas de precio es de F4, `Pos.tsx`). No hay nada del lado de la API que resuelva un
# precio a partir de un `price_list_id` para poder probarlo acá.


def test_staff_can_run_full_pos_flow(admin_client, staff_client):
    """El catalogo/stock lo carga un admin; el flujo de venta lo corre staff."""
    item_id = _make_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "5")

    abrir_turno(staff_client)
    venta = registrar_venta(staff_client, item_id, cantidad="2")
    assert venta["estado"] == "cobrada"


# 🔴 **Retirados, invariante de borrador incremental**: `test_remove_item_recalculates_total`,
# `test_remove_last_item_leaves_empty_sale_that_cannot_be_confirmed`,
# `test_remove_item_out_of_range_is_404`, `test_update_item_quantity_recalculates_total`,
# `test_update_item_quantity_keeps_the_frozen_unit_price` y `test_cannot_edit_a_confirmed_sale`
# probaban corregir el ticket ANTES de cobrar -- quitar una línea, ajustar una cantidad -- y que
# una venta ya cobrada quedara inmutable. D1 borró el borrador editable: la corrección de un
# error de carga pasa a ser responsabilidad del navegador (F4, antes de mandar `POST
# /api/ventas`) o, después de cobrada, una devolución (`POST /api/ventas/{vid}/devolver`, ver
# `tests/test_devoluciones.py`) -- no una edición. No queda ningún endpoint de edición de línea
# contra el que portar estos tests: los seis contestarían 410 sobre rutas que ya no representan
# ninguna operación del dominio nuevo.


def test_update_item_quantity_rejects_zero_and_negative(admin_client):
    """🔴 **Invariante cambiado, no retirado.** El modelo viejo rechazaba con 409 corregir una
    línea a cantidad cero o negativa. `POST /api/ventas` no corrige líneas -- las arma todas
    juntas -- y una línea con `qty <= 0` se **descarta en silencio** (`crear()`: `for i in
    payload.items if i.nombre.strip() and i.qty > 0`), no se rechaza. El invariante que
    sobrevive es el de más arriba (`test_confirm_without_items_fails`): si la venta se queda sin
    ninguna línea válida, ahí sí es 422. Se afirma esa forma nueva."""
    abrir_turno(admin_client)
    item_id = _make_item(admin_client)
    respuesta = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 0, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "efectivo", "monto": 0}],
    })
    assert respuesta.status_code == 422


# --- cobro: pago mixto y vuelto -----------------------------------------


def _venta_lista_items(cantidad="2", precio="1500.00"):
    return [{"nombre": "línea", "qty": float(cantidad), "precio": float(precio), "producto_id": None}]


def test_cash_payment_records_the_change(admin_client):
    """D4: el vuelto se guarda (`ventas_pagos.recibido`), pero la API no lo precomputa -- a
    diferencia del modelo viejo (`SalePaymentOut.vuelto`, una property del dominio), acá
    `recibido` es la única columna nueva y el vuelto es `recibido - monto`, a cargo de quien
    lea (ver D4, DECISIONS.md ADR-025)."""
    item_id = _make_item(admin_client)
    abrir_turno(admin_client)
    venta = registrar_venta(
        admin_client, item_id, cantidad="2", precio="1500.00",
        pagos=[{"medio": "efectivo", "monto": 3000.00, "recibido": 5000.00}],
    )
    assert venta["estado"] == "cobrada"
    pago = venta["pagos"][0]
    assert float(pago["recibido"]) == 5000.0
    assert float(pago["recibido"]) - float(pago["monto"]) == 2000.0


def test_mixed_payment_is_persisted_per_method(admin_client):
    item_id = _make_item(admin_client)
    abrir_turno(admin_client)
    venta = registrar_venta(
        admin_client, item_id, cantidad="2", precio="1500.00",
        pagos=[
            {"medio": "efectivo", "monto": 1000.00, "recibido": 1000.00},
            {"medio": "tarjeta_debito", "monto": 2000.00, "referencia": "lote 7"},
        ],
    )
    pagos = venta["pagos"]
    assert [p["medio"] for p in pagos] == ["efectivo", "tarjeta_debito"]
    assert pagos[1]["recibido"] is None
    assert pagos[1]["referencia"] == "lote 7"

    # sobrevive a releer la venta, no solo en la respuesta de POST
    releida = admin_client.get(f"/api/ventas/{venta['id']}")
    assert len(releida.json()["pagos"]) == 2


def test_payments_below_total_are_rejected(admin_client):
    """Cerrado en libracommerce v0.16.2: `OpcionesVentas.exigir_pago_completo`
    (prendida en `app/main.py`) rechaza con 422 -- no 409, que es el código
    del modelo viejo -- una venta cuyos pagos declarados no cubren el total,
    antes de escribir nada."""
    _make_item(admin_client)
    abrir_turno(admin_client)
    respuesta = admin_client.post("/api/ventas", json={
        "fecha": hoy(), "items": _venta_lista_items(),
        "pagos": [{"medio": "efectivo", "monto": 1000.00}],
    })
    assert respuesta.status_code == 422, respuesta.text
    assert "no cubren el total" in respuesta.json()["detail"]


def test_received_less_than_the_payment_is_rejected(admin_client):
    """Cerrado en libracommerce v0.16.2: `PagoPayload` valida `recibido >=
    monto` -- un vuelto negativo es un dato imposible."""
    _make_item(admin_client)
    abrir_turno(admin_client)
    respuesta = admin_client.post("/api/ventas", json={
        "fecha": hoy(), "items": _venta_lista_items(),
        "pagos": [{"medio": "efectivo", "monto": 3000.00, "recibido": 2000.00}],
    })
    assert respuesta.status_code == 422


def test_confirm_without_any_payment_info_is_rejected(admin_client):
    _make_item(admin_client)
    abrir_turno(admin_client)
    respuesta = admin_client.post("/api/ventas", json={
        "fecha": hoy(), "items": _venta_lista_items(), "pagos": [],
    })
    assert respuesta.status_code == 422


# 🔴 **Retirado, invariante ya no aplica**: `test_single_medio_pago_still_works_and_records_no_
# payments` probaba el atajo del modelo viejo (`medio_pago` suelto en vez de la lista `pagos`,
# que confirmaba sin dejar ninguna fila de pago). D1 no tiene atajo: `POST /api/ventas` siempre
# recibe `pagos` como lista, y cada pago -- sea uno solo o varios -- queda como una fila de
# `ventas_pagos` (ver `test_mixed_payment_is_persisted_per_method` y
# `test_full_pos_flow_confirms_sale_and_decrements_stock`, que ya cubren "un solo medio,
# registrado").


def test_mixed_payment_creates_one_caja_movement_per_method(admin_client):
    """La caja tiene que poder decir cuanto entro por cada medio: es lo que
    se arquea. Un solo movimiento con el total no serviria."""
    from libracore.db import caja as db_caja

    item_id = _make_item(admin_client)
    abrir_turno(admin_client)
    venta = registrar_venta(
        admin_client, item_id, cantidad="2", precio="1500.00",
        pagos=[
            {"medio": "efectivo", "monto": 1000.00},
            {"medio": "tarjeta_debito", "monto": 2000.00},
        ],
    )

    numero = venta["numero"]
    nuevos = [m for m in db_caja.get_caja_movimientos() if m["concepto"].startswith(f"Venta {numero}")]
    assert len(nuevos) == 2
    assert sorted(m["medio_pago"] for m in nuevos) == ["efectivo", "tarjeta_debito"]
    assert sorted(float(m["monto"]) for m in nuevos) == [1000.0, 2000.0]


# --- turno de caja -------------------------------------------------------


def test_cobrar_sin_turno_abierto_es_rechazado(admin_client):
    """La regla que sostiene el arqueo: una venta fuera de turno seria plata
    sin control de caja."""
    item_id = _make_item(admin_client)
    respuesta = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 1, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "efectivo", "monto": 1500.0}],
    })
    assert respuesta.status_code == 409
    assert "turno" in respuesta.json()["detail"]


def test_no_se_puede_abrir_un_turno_sobre_otro(admin_client):
    abrir_turno(admin_client)
    segundo = admin_client.post("/shifts/open", json={"monto_inicial": 100})
    assert segundo.status_code == 409


def test_turno_actual_arranca_vacio_y_despues_reporta_el_abierto(admin_client):
    assert admin_client.get("/shifts/current").json()["turno"] is None
    tid = abrir_turno(admin_client, 5000)
    actual = admin_client.get("/shifts/current").json()
    assert actual["turno"]["id"] == tid
    assert actual["turno"]["estado"] == "abierto"
    assert actual["resumen"]["total_ventas"] == 0


def test_el_cobro_queda_dentro_del_turno_y_suma_al_arqueo(admin_client):
    """El arqueo se cuenta sobre la caja: cada medio entra por separado."""
    item_id = _make_item(admin_client)
    tid = abrir_turno(admin_client)
    registrar_venta(
        admin_client, item_id, cantidad="2", precio="1500.00",
        pagos=[
            {"medio": "efectivo", "monto": 1000.00, "recibido": 2000.00},
            {"medio": "tarjeta_debito", "monto": 2000.00},
        ],
    )

    resumen = admin_client.get(f"/shifts/{tid}/summary").json()["resumen"]
    assert resumen["pagos_por_medio"] == {"efectivo": 1000.0, "tarjeta_debito": 2000.0}
    # el vuelto NO entra a la caja: entraron 1000 de efectivo, no 2000
    assert resumen["efectivo_ventas"] == 1000.0
    assert resumen["total_ventas"] == 3000.0


def test_cierre_calcula_esperado_y_conserva_la_diferencia(admin_client):
    item_id = _make_item(admin_client)
    tid = abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, cantidad="2", precio="1500.00")

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
    tid = abrir_turno(admin_client)
    assert admin_client.post(f"/shifts/{tid}/close", json={"monto_declarado": 0}).status_code == 200
    repetido = admin_client.post(f"/shifts/{tid}/close", json={"monto_declarado": 0})
    assert repetido.status_code == 409


def test_despues_de_cerrar_no_se_puede_cobrar_hasta_abrir_otro(admin_client):
    item_id = _make_item(admin_client)
    tid = abrir_turno(admin_client)
    admin_client.post(f"/shifts/{tid}/close", json={"monto_declarado": 0})

    respuesta = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 1, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "efectivo", "monto": 1500.0}],
    })
    assert respuesta.status_code == 409

    abrir_turno(admin_client)
    cobrada = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 1, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "efectivo", "monto": 1500.0}],
    })
    assert cobrada.status_code == 200, cobrada.text


def test_cerrar_un_turno_inexistente_es_404(admin_client):
    assert admin_client.post("/shifts/9999/close", json={"monto_declarado": 0}).status_code == 404


# --- depósito de la venta (F4, VentaLibra multisucursal, ADR-025) ---------
#
# El POS manda `deposito_id` = el depósito de la sucursal elegida en pantalla
# (`GET /locations` -- en este producto un "location" ES un depósito del
# motor, mismo `id`: `app/services/locations.py::LocationService` envuelve el
# MISMO repositorio y la MISMA tabla `locations` que lee `libracommerce.erp.
# catalogo.get_deposito`). Sin el campo (el default, `None`), el motor sigue
# descontando del default de siempre -- eso ya lo cubre el resto de este
# archivo. Acá se afirma el campo aditivo en sí.


def test_deposito_id_descuenta_del_deposito_elegido_no_del_default(admin_client):
    item_id = _make_item(admin_client)
    default_id = deposito_default(admin_client)
    otro = admin_client.post("/locations", json={"name": "Sucursal Once"}).json()
    con_stock(admin_client, item_id, otro["id"], "10")
    con_stock(admin_client, item_id, default_id, "10")
    abrir_turno(admin_client)

    venta = registrar_venta(admin_client, item_id, cantidad="3", deposito_id=otro["id"])
    assert venta["estado"] == "cobrada"

    assert stock(admin_client, item_id, otro["id"]) == 7
    # El default no se tocó: la venta declaró un depósito propio.
    assert stock(admin_client, item_id, default_id) == 10


def test_deposito_id_inexistente_es_422_y_no_registra_nada(admin_client):
    item_id = _make_item(admin_client)
    default_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, default_id, "10")
    abrir_turno(admin_client)

    venta = registrar_venta(
        admin_client, item_id, cantidad="1", deposito_id=999999, esperar=422,
    )
    assert "999999" in venta["detail"]
    # Ni el stock ni la caja se movieron: la validación corre antes de escribir.
    assert stock(admin_client, item_id, default_id) == 10
