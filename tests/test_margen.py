"""Margen y rotación con el router del motor (`/api/reportes/margen`, tanda 1 del roadmap de producto, ADR-045).

`libracommerce.web.margen_router.build_margen_router`, sólo lectura: la cuenta (qué es una venta, cómo se restan las devoluciones,
de dónde sale el costo, cómo se reparte el descuento) es del motor y se prueba allá a fondo. Acá se prueba el CABLEADO: que está
montado, que es de admin, y que sobre las ventas de este producto —las que escribe `POST /api/ventas`— da lo que dice.

🔴 `POST /api/ventas` guarda el costo de la línea desde `libracommerce` v0.27.0 (`OpcionesVentas.guardar_costo`, ADR-050):
`sale_items.unit_cost_snapshot` = el `default_cost` de ese momento, y el margen de esas ventas ya no es estimado. Las ventas
anteriores (snapshot NULL, sin backfill) siguen saliendo con el costo de HOY y marcadas `costo_estimado`: los tests del final
arman una así, poniendo el snapshot en NULL a mano.
"""
from ventas_helpers import caja_default, hoy, registrar_venta


def _abrir_turno(client):
    abierto = client.post("/api/turnos/abrir", json={"monto_inicial": 0, "caja_id": caja_default(client)})
    assert abierto.status_code == 200, abierto.text


def _make_item(client, name="Fideos 500g", price="1500.00", cost="900.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post(
        "/api/productos", json={"nombre": name, "unidad": "u", "precio_venta": price, "precio_costo": cost},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _snapshots(client, sale_id):
    """`unit_cost_snapshot` de las líneas de una venta, en orden, como lo dejó `POST /api/ventas`."""
    filas = client.app.state.conn.execute(
        "SELECT unit_cost_snapshot FROM sale_items WHERE sale_id = ? ORDER BY id", (sale_id,),
    ).fetchall()
    return [None if f[0] is None else float(f[0]) for f in filas]


def _margen(client, **params):
    r = client.get("/api/reportes/margen", params={"desde": hoy(), "hasta": hoy(), **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_el_margen_sale_de_las_ventas_de_este_producto(admin_client):
    item_id = _make_item(admin_client)
    _abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, precio="1500.00", cantidad="2")

    m = _margen(admin_client)
    (p,) = m["productos"]
    # 2 u a $1500 con costo $900: ingreso 3000, costo 1800, margen 1200 (40 %).
    assert (p["producto_id"], p["nombre"], p["unidades"], p["ingreso"], p["costo"], p["margen"], p["margen_pct"]) == (
        item_id, "Fideos 500g", 2.0, 3000.0, 1800.0, 1200.0, 40.0)
    assert p["unidades_por_dia"] == 2.0  # el rango es un solo día
    assert m["periodos"][0]["periodo"] == hoy() and m["periodos"][0]["unidades"] == 2.0
    assert m["resumen"]["margen"] == 1200.0 and m["resumen"]["productos"] == 1
    # La venta guardó su costo (ADR-050): el margen es el de aquella venta, no una estimación con el costo de hoy.
    assert p["costo_estimado"] is False and m["resumen"]["productos_costo_estimado"] == 0


def test_una_venta_anulada_no_es_una_venta(admin_client):
    item_id = _make_item(admin_client)
    _abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, precio="1500.00", cantidad="1")
    mala = registrar_venta(admin_client, item_id, precio="1500.00", cantidad="5")
    assert admin_client.post(f"/api/ventas/{mala['id']}/anular").status_code == 200

    assert _margen(admin_client)["resumen"]["unidades"] == 1.0


def test_fiar_es_vender(admin_client):
    """A diferencia de la caja (`sin_fiado`), el margen es de lo vendido: una venta a cuenta corriente entra."""
    item_id = _make_item(admin_client)
    cliente = admin_client.post("/api/clientes", json={"name": "Kiosco"}).json()["id"]
    _abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, precio="1500.00", cantidad="1", cliente_id=cliente,
                    pagos=[{"medio": "cuenta_corriente", "monto": 1500.0}])

    assert _margen(admin_client)["resumen"]["ingreso"] == 1500.0


def test_export_csv_bajo_el_mismo_prefijo(admin_client):
    item_id = _make_item(admin_client)
    _abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, precio="1500.00", cantidad="2")

    r = admin_client.get("/api/reportes/margen/export/productos", params={"desde": hoy(), "hasta": hoy()})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[1].startswith(f"{item_id},Fideos 500g,2.0,")
    assert admin_client.get("/api/reportes/margen/export/periodos").status_code == 200


def test_un_parametro_invalido_es_422(admin_client):
    assert admin_client.get("/api/reportes/margen", params={"orden": "inventado"}).status_code == 422


def test_el_reporte_de_ventas_de_siempre_sigue_donde_estaba(admin_client):
    """El margen cuelga de `/api/reportes/margen`; no le pisa la ruta a `/api/reportes` ni a `/caja-medios`."""
    assert admin_client.get("/api/reportes").status_code == 200
    assert admin_client.get("/api/reportes/caja-medios").status_code == 200


def test_un_cajero_no_ve_el_costo_ni_el_margen(cajero_client):
    assert cajero_client.get("/api/reportes/margen").status_code == 403
    assert cajero_client.get("/api/reportes/margen/export/productos").status_code == 403
    assert cajero_client.get("/api/reportes/margen/export/periodos").status_code == 403


def test_el_margen_esta_libre_en_todos_los_planes(admin_client):
    """Decidido el 2026-09-29 (ADR-048, que resuelve el pendiente de ADR-046): el margen y la rotación son libres en Básico
    y en Premium. El plan se distingue por facturación y multisucursal; no hay `require_module` sobre esta ruta."""
    for modulo in ("facturacion", "multisucursal"):
        admin_client.app.state.modules.set_enabled(modulo, False)
    assert admin_client.get("/api/reportes/margen").status_code == 200


def test_la_venta_guarda_el_costo_del_momento_y_un_cambio_de_costo_no_la_reescribe(admin_client):
    """ADR-050: `POST /api/ventas` escribe `sale_items.unit_cost_snapshot` con el costo vigente; subir el costo del producto
    después no toca la venta ya hecha (ni su margen), y la venta siguiente guarda el costo nuevo."""
    item_id = _make_item(admin_client, cost="900.00")
    _abrir_turno(admin_client)
    primera = registrar_venta(admin_client, item_id, precio="1500.00", cantidad="2")
    assert _snapshots(admin_client, primera["id"]) == [900.0]

    cambiado = admin_client.put(f"/api/productos/{item_id}", json={
        "nombre": "Fideos 500g", "codigo": "", "descripcion": "", "precio_venta": 1500.0, "precio_costo": 1200.0,
        "unidad": "u", "categoria": "", "stock_minimo": 0, "tipo": "producto", "vendible": True, "activo": True,
    })
    assert cambiado.status_code == 200, cambiado.text
    assert _snapshots(admin_client, primera["id"]) == [900.0]
    (p,) = _margen(admin_client)["productos"]
    assert p["costo"] == 1800.0 and p["margen"] == 1200.0 and p["costo_estimado"] is False  # 2 u a $900, no a $1200

    segunda = registrar_venta(admin_client, item_id, precio="1500.00", cantidad="1")
    assert _snapshots(admin_client, segunda["id"]) == [1200.0]
    (p,) = _margen(admin_client)["productos"]
    assert p["costo"] == 3000.0 and p["costo_estimado"] is False  # 1800 de la primera + 1200 de la segunda


def test_un_producto_sin_costo_guarda_el_snapshot_vacio_y_el_margen_lo_avisa(admin_client):
    """Sin costo cargado no hay nada que guardar: el snapshot queda NULL (no un 0 que pase por costo real) y el reporte lo
    marca `sin_costo`, no `costo_estimado`."""
    item_id = _make_item(admin_client, name="Sin costo", cost="0")
    _abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id, precio="1500.00", cantidad="1")
    assert _snapshots(admin_client, venta["id"]) == [None]

    m = _margen(admin_client)
    (p,) = m["productos"]
    assert p["sin_costo"] is True and p["costo_estimado"] is False
    assert m["resumen"]["productos_sin_costo"] == 1 and m["resumen"]["productos_costo_estimado"] == 0


def test_una_venta_anterior_sin_snapshot_sigue_marcada_como_estimada(admin_client):
    """Sin backfill (ADR-050): la línea con `unit_cost_snapshot` NULL —las de antes de v0.27.0— usa el costo de HOY y sale
    `costo_estimado`; la línea de una venta nueva, del mismo reporte, no."""
    nueva_id = _make_item(admin_client, name="Nueva", cost="900.00")
    vieja_id = _make_item(admin_client, name="Vieja", cost="500.00")
    _abrir_turno(admin_client)
    registrar_venta(admin_client, nueva_id, precio="1500.00", cantidad="1")
    vieja = registrar_venta(admin_client, vieja_id, precio="1000.00", cantidad="1")
    conn = admin_client.app.state.conn
    conn.execute("UPDATE sale_items SET unit_cost_snapshot = NULL WHERE sale_id = ?", (vieja["id"],))
    conn.commit()

    m = _margen(admin_client)
    por_nombre = {p["nombre"]: p for p in m["productos"]}
    assert por_nombre["Nueva"]["costo_estimado"] is False and por_nombre["Nueva"]["costo"] == 900.0
    assert por_nombre["Vieja"]["costo_estimado"] is True and por_nombre["Vieja"]["costo"] == 500.0
    assert m["resumen"]["productos_costo_estimado"] == 1
