"""Reportes de ventas, caja y stock: `app/services/reports.py` es propio de
VentaLibra y F3 no lo toca (D6 -- catálogo/listas/reportes a las factories de
LibraCommerce -- queda fuera de esta fase por tamaño; ver el reporte de F3).
Lo que cambió es CÓMO se registra la venta que el reporte después agrupa:
`POST /api/ventas` (D1, una sola llamada) en vez de borrador + confirmar.
"""
import secrets
from datetime import date, timedelta

from ventas_helpers import hoy


def _abrir_turno(client, monto_inicial=0):
    """Sin turno abierto, registrar una venta da 409: una venta fuera de
    turno sería plata sin control de caja."""
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


def _confirmed_sale(client, item_id, location_id, quantity="1", price="1500.00", name="línea"):  # noqa: ARG001
    """Registra una venta de una línea, en una sola llamada (D1).

    `location_id` se mantiene en la firma (no se usa: `POST /api/ventas` no
    pide depósito -- el motor descuenta stock a través de `erp.stock`, que
    resuelve el depósito por su cuenta) para no reescribir cada call site del
    archivo; queda documentado acá por qué el parámetro no viaja.

    `name` es el `nombre` de la línea (`description_snapshot` en el
    resultado): el payload no lo resuelve solo desde el catálogo -- a
    diferencia del modelo viejo, acá es texto libre por línea (mismo criterio
    que Contalibra) -- así que un test que verifique la descripción tiene que
    mandar la misma que le puso al ítem.
    """
    _abrir_turno(client)
    return client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": name, "qty": float(quantity), "precio": float(price), "producto_id": item_id}],
        "pagos": [{"medio": "efectivo", "monto": float(quantity) * float(price)}],
    })


def _today_range():
    """Ventana de "hoy" para los reportes -- misma `hoy()` (hora de Argentina)
    que usa `_confirmed_sale()` para fechar la venta, no `date.today()` del
    proceso: si difieren, la venta cae fuera de la ventana y el reporte da
    vacío sin que haya ningún bug (el corrimiento de fecha real del
    2026-09-15 rompió estos tests exactamente así)."""
    today = hoy()
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


def _mover_occurred_on(client, sale_id, fecha):
    conn = client.app.state.conn
    conn.execute("UPDATE sales SET occurred_on = ? WHERE id = ?", (fecha, sale_id))
    conn.commit()


def test_el_reporte_agrupa_por_occurred_on_no_por_confirmed_at(admin_client):
    """🔴 **F3 cambia dónde vive el defecto que ADR-016 cerró el 2026-08-24,
    no lo reintroduce.**

    Hasta acá el reporte filtraba `confirmed_at` (UTC) con una ventana
    convertida a hora local, justamente para que una venta de las 22:00 no
    quedara contada en el día siguiente. Desde F3, `libracommerce.erp.
    ventas.crear_venta` -- que es quien registra la venta ahora -- **nunca
    escribe `confirmed_at`**: sólo `occurred_on`, que llega ya en la fecha
    LOCAL (`VentaPayload.fecha`). Sin este cambio en `app/services/
    reports.py`, toda venta nueva quedaba fuera de todos los reportes, sin
    ningún error -- el riesgo que ADR-025 dejó anotado ("el reporte tiene
    que sobrevivir al pasaje").

    La conversión de huso ya no la hace el reporte: la hace quien pone
    `occurred_on` (el caller, al crear; la migración `0003`, para las ventas
    viejas -- ver `tests/test_migracion_0003.py`, que cubre exactamente el
    caso de cruce de medianoche). Acá sólo se verifica que el reporte
    agrupa por esa columna, no por `confirmed_at`.
    """
    item_id = _make_item(admin_client, price="1000.00")
    location_id = _make_location(admin_client)
    confirmed = _confirmed_sale(admin_client, item_id, location_id, price="1000.00")
    assert confirmed.status_code == 200, confirmed.text
    # La venta nueva no escribe confirmed_at.
    conn = admin_client.app.state.conn
    fila = conn.execute(
        "SELECT confirmed_at, occurred_on FROM sales WHERE id = ?", (confirmed.json()["id"],),
    ).fetchone()
    assert fila[0] is None
    assert fila[1] == hoy()

    _mover_occurred_on(admin_client, confirmed.json()["id"], "2026-03-14")

    en_el_dia = admin_client.get(
        "/reports/sales", params={"date_from": "2026-03-14", "date_to": "2026-03-14"})
    assert en_el_dia.json()["total_ventas"] == 1

    # 🔑 El control negativo: sin filtrar de verdad por `occurred_on`, la
    # venta seguiría apareciendo en cualquier rango (o en el de "hoy").
    otro_dia = admin_client.get(
        "/reports/sales", params={"date_from": "2026-03-15", "date_to": "2026-03-15"})
    assert otro_dia.json()["total_ventas"] == 0


def test_sales_report_ignores_draft_sales(admin_client):
    """Un borrador que nunca se registró no cuenta.

    D1 no deja un borrador vía API (`POST /api/ventas` registra completo en
    una sola llamada): se escribe directo en la base, con la misma forma que
    dejaba `POST /sales` antes de F3.
    """
    conn = admin_client.app.state.conn
    conn.execute(
        "INSERT INTO sales (number, status, source_type, subtotal, total) "
        "VALUES (?, 'draft', 'pos', 0, 0)", (f"POS-{secrets.token_hex(4)}",),
    )
    conn.commit()

    response = admin_client.get("/reports/sales", params=_today_range())
    assert response.status_code == 200
    assert response.json()["total_ventas"] == 0


def test_sales_report_top_items_reflects_confirmed_sale(admin_client):
    item_id = _make_item(admin_client, name="Yerba 1kg", price="2000.00")
    location_id = _make_location(admin_client)
    _confirmed_sale(admin_client, item_id, location_id, quantity="3", price="2000.00", name="Yerba 1kg")

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

    hoy_date = date.fromisoformat(hoy())
    yesterday = (hoy_date - timedelta(days=2)).isoformat()
    day_before = (hoy_date - timedelta(days=5)).isoformat()
    response = admin_client.get(
        "/reports/sales", params={"date_from": day_before, "date_to": yesterday},
    )
    assert response.json()["total_ventas"] == 0


def test_caja_report_reflects_confirmed_sale_payment(admin_client):
    item_id = _make_item(admin_client, price="500.00")
    location_id = _make_location(admin_client)
    _confirmed_sale(admin_client, item_id, location_id, price="500.00")

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
