"""Reportes con el router del motor (`/api/reportes`, fase 8, ADR-035).

Hasta la fase 8 esto era `/reports/{sales,caja,stock}` (`app/routers/reports.py` + `services/reports.py`). Ahora es
`libracore.reportes_router.build_reportes_router` sobre las ventas de LibraCommerce (`libracommerce.erp.reportes`), el mismo de
Contalibra, con dos variantes: una venta anulada o pendiente de cobro no es una venta, y fiar no es cobrar (la cuenta corriente no
es ingreso de caja). Sólo admin.
"""
import secrets
from datetime import date, timedelta

from ventas_helpers import ajustar, caja_default, crear_ubicacion, hoy, registrar_venta


def _abrir_turno(client, monto_inicial=0):
    """Sin turno abierto, registrar una venta da 409: una venta fuera de
    turno sería plata sin control de caja."""
    abierto = client.post(
        "/api/turnos/abrir", json={"monto_inicial": monto_inicial, "caja_id": caja_default(client)}
    )
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["id"]


def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post(
        "/api/productos",
        json={"nombre": name, "unidad": "u", "precio_venta": price, "precio_costo": "900.00"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _make_location(client, name="Sucursal 1"):
    return crear_ubicacion(client, name)["id"]


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


def _reporte(client, **params):
    r = client.get("/api/reportes", params={"desde": hoy(), "hasta": hoy(), **params})
    assert r.status_code == 200, r.text
    return r.json()


def _ventas_del_dia(reporte) -> tuple[int, float]:
    return sum(v["cantidad"] for v in reporte["ventas_ts"]), sum(float(v["total"]) for v in reporte["ventas_ts"])


def test_sales_report_totals_confirmed_sale(admin_client):
    item_id = _make_item(admin_client, price="1500.00")
    location_id = _make_location(admin_client)
    confirmed = _confirmed_sale(admin_client, item_id, location_id, quantity="2")
    assert confirmed.status_code == 200, confirmed.text

    reporte = _reporte(admin_client)
    assert _ventas_del_dia(reporte) == (1, 3000.0)
    assert reporte["resumen"]["ventas_cantidad"] == 1 and float(reporte["resumen"]["ventas_total"]) == 3000.0
    assert len(reporte["ventas_ts"]) == 1 and reporte["ventas_ts"][0]["periodo"] == hoy()


def _mover_occurred_on(client, sale_id, fecha):
    conn = client.app.state.conn
    conn.execute("UPDATE sales SET occurred_on = ? WHERE id = ?", (fecha, sale_id))
    conn.commit()


def test_el_reporte_agrupa_por_occurred_on_no_por_confirmed_at(admin_client):
    """🔴 `libracommerce.erp.ventas.crear_venta` **nunca escribe `confirmed_at`**: sólo `occurred_on`, que llega ya en la fecha LOCAL.
    Un reporte que filtrara `confirmed_at` dejaría toda venta nueva afuera, sin ningún error (ADR-025). Acá se verifica que agrupa por
    `occurred_on`."""
    item_id = _make_item(admin_client, price="1000.00")
    location_id = _make_location(admin_client)
    confirmed = _confirmed_sale(admin_client, item_id, location_id, price="1000.00")
    assert confirmed.status_code == 200, confirmed.text
    conn = admin_client.app.state.conn
    fila = conn.execute(
        "SELECT confirmed_at, occurred_on FROM sales WHERE id = ?", (confirmed.json()["id"],),
    ).fetchone()
    assert fila[0] is None and fila[1] == hoy()

    _mover_occurred_on(admin_client, confirmed.json()["id"], "2026-03-14")

    assert _ventas_del_dia(_reporte(admin_client, desde="2026-03-14", hasta="2026-03-14"))[0] == 1
    # 🔑 El control negativo: sin filtrar de verdad por `occurred_on`, la venta seguiría apareciendo en cualquier rango.
    assert _ventas_del_dia(_reporte(admin_client, desde="2026-03-15", hasta="2026-03-15"))[0] == 0


def test_sales_report_ignores_draft_sales(admin_client):
    """Un borrador (una venta pendiente de cobro, p. ej. un QR sin acreditar) no es una venta: no cuenta."""
    conn = admin_client.app.state.conn
    conn.execute(
        "INSERT INTO sales (number, status, source_type, subtotal, total, occurred_on) "
        "VALUES (?, 'draft', 'pos', 0, 500, ?)", (f"POS-{secrets.token_hex(4)}", hoy()),
    )
    conn.commit()

    reporte = _reporte(admin_client)
    assert _ventas_del_dia(reporte)[0] == 0 and reporte["resumen"]["ventas_cantidad"] == 0


def test_una_venta_anulada_no_cuenta(admin_client):
    """🔴 El motor de Contalibra cuenta todo lo que hay en `sales`; acá `solo_confirmadas` deja afuera lo anulado."""
    item_id = _make_item(admin_client, price="1000.00")
    location_id = _make_location(admin_client)
    buena = _confirmed_sale(admin_client, item_id, location_id, price="1000.00")
    mala = registrar_venta(admin_client, item_id, precio="1000.00", cantidad="1")
    anulada = admin_client.post(f"/api/ventas/{mala['id']}/anular")
    assert anulada.status_code == 200, anulada.text

    reporte = _reporte(admin_client)
    assert _ventas_del_dia(reporte) == (1, 1000.0)
    assert reporte["resumen"]["ventas_cantidad"] == 1
    assert sum(float(m["total"]) for m in reporte["medios"]) == 1000.0
    assert buena.status_code == 200


def test_sales_report_top_items_reflects_confirmed_sale(admin_client):
    item_id = _make_item(admin_client, name="Yerba 1kg", price="2000.00")
    location_id = _make_location(admin_client)
    _confirmed_sale(admin_client, item_id, location_id, quantity="3", price="2000.00", name="Yerba 1kg")

    productos = _reporte(admin_client)["productos"]
    assert len(productos) == 1
    assert productos[0]["nombre"] == "Yerba 1kg"
    assert float(productos[0]["cantidad"]) == 3.0
    assert float(productos[0]["total"]) == 6000.0


def test_sales_report_excludes_dates_outside_range(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    _confirmed_sale(admin_client, item_id, location_id)

    hoy_date = date.fromisoformat(hoy())
    yesterday = (hoy_date - timedelta(days=2)).isoformat()
    day_before = (hoy_date - timedelta(days=5)).isoformat()
    assert _ventas_del_dia(_reporte(admin_client, desde=day_before, hasta=yesterday))[0] == 0


def test_caja_report_reflects_confirmed_sale_payment(admin_client):
    item_id = _make_item(admin_client, price="500.00")
    location_id = _make_location(admin_client)
    _confirmed_sale(admin_client, item_id, location_id, price="500.00")

    reporte = _reporte(admin_client)
    ingresos = next(c for c in reporte["caja"] if c["tipo"] == "ingreso")
    assert float(ingresos["total"]) == 500.0
    assert float(reporte["resumen"]["caja_saldo"]) == 500.0


def test_fiar_no_es_cobrar_la_cuenta_corriente_no_es_ingreso_de_caja(admin_client):
    """🔴 La capa ERP escribe un movimiento de caja por cada medio, cuenta corriente incluido. Sin `sin_fiado` el reporte sumaría la deuda
    como plata en el cajón y dejaría de coincidir con el arqueo del turno (ADR-027)."""
    item_id = _make_item(admin_client, price="1000.00")
    cliente = admin_client.post("/api/clientes", json={"name": "Kiosco"}).json()["id"]
    _abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, precio="1000.00", cantidad="1")  # efectivo: 1000
    registrar_venta(admin_client, item_id, precio="2000.00", cantidad="1", cliente_id=cliente,
                    pagos=[{"medio": "cuenta_corriente", "monto": 2000.0}])

    reporte = _reporte(admin_client)
    assert _ventas_del_dia(reporte) == (2, 3000.0)  # las dos son ventas
    ingresos = next(c for c in reporte["caja"] if c["tipo"] == "ingreso")
    assert float(ingresos["total"]) == 1000.0  # pero sólo una entró al cajón
    assert float(reporte["resumen"]["caja_saldo"]) == 1000.0
    # Y como medio de venta sí se ve: la venta fue a cuenta corriente.
    assert "cuenta_corriente" in {m["medio"] for m in reporte["medios"]}
    # La caja por medio tampoco lo trae, y su saldo es el del arqueo.
    pivot = admin_client.get("/api/reportes/caja-medios", params={"desde": hoy(), "hasta": hoy()}).json()
    assert "cuenta_corriente" not in pivot["totales"]
    assert sum(c["saldo"] for c in pivot["cajas"]) == 1000.0


def test_la_caja_por_medio_separa_cada_mostrador(admin_client):
    item_id = _make_item(admin_client, price="500.00")
    _abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, precio="500.00", cantidad="1")
    pivot = admin_client.get("/api/reportes/caja-medios", params={"desde": hoy(), "hasta": hoy()}).json()
    assert [c["id"] for c in pivot["cajas"]] == [caja_default(admin_client)]
    assert pivot["totales"]["efectivo"]["ingresos"] == 500.0
    assert pivot["cajas_config"] and pivot["medio_label"]["efectivo"] == "Efectivo"


def test_los_exports_csv(admin_client):
    item_id = _make_item(admin_client, name="Yerba 1kg", price="500.00")
    _abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, precio="500.00", cantidad="2")
    ventas = admin_client.get("/reportes/export/ventas", params={"desde": hoy(), "hasta": hoy()})
    assert ventas.status_code == 200 and "periodo,cantidad,total" in ventas.text and hoy() in ventas.text
    assert "Yerba" in admin_client.get("/reportes/export/productos").text or "línea" in admin_client.get("/reportes/export/productos").text
    assert "efectivo" in admin_client.get("/reportes/export/medios").text
    assert "Caja,Medio de cobro" in admin_client.get("/reportes/caja-medios/export").text


def test_el_stock_bajo_es_el_de_los_minimos(admin_client):
    """`stock_bajo` son los productos por debajo de SU mínimo (el que se carga en Productos), no un umbral global en cero."""
    item_id = _make_item(admin_client, name="Arroz 1kg")
    location_id = _make_location(admin_client)
    ajustar(admin_client, item_id, location_id, "2")
    assert _reporte(admin_client)["stock_bajo"] == []  # sin mínimo no hay «bajo»
    _make_unit_and_min = admin_client.get("/api/productos").json()[0]
    r = admin_client.put(f"/api/productos/{item_id}", json={
        "nombre": "Arroz 1kg", "unidad": "u", "codigo": "", "precio_venta": 1500, "precio_costo": 900, "stock_minimo": 5})
    assert r.status_code == 200, r.text
    bajo = _reporte(admin_client)["stock_bajo"]
    assert [(b["nombre"], float(b["stock_actual"]), float(b["stock_minimo"])) for b in bajo] == [("Arroz 1kg", 2.0, 5.0)]
    assert _make_unit_and_min["id"] == item_id


def test_staff_cannot_access_reports(staff_client):
    assert staff_client.get("/api/reportes", params={"desde": hoy(), "hasta": hoy()}).status_code == 403
    assert staff_client.get("/api/reportes/caja-medios").status_code == 403
    assert staff_client.get("/reportes/export/ventas").status_code == 403


def test_las_rutas_viejas_ya_no_existen(admin_client):
    for ruta in ("/reports/sales", "/reports/caja", "/reports/stock"):
        assert admin_client.get(ruta, params=_today_range()).status_code in (404, 405), ruta
