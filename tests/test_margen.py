"""Margen y rotación con el router del motor (`/api/reportes/margen`, tanda 1 del roadmap de producto, ADR-045).

`libracommerce.web.margen_router.build_margen_router`, sólo lectura: la cuenta (qué es una venta, cómo se restan las devoluciones,
de dónde sale el costo, cómo se reparte el descuento) es del motor y se prueba allá a fondo. Acá se prueba el CABLEADO: que está
montado, que es de admin, y que sobre las ventas de este producto —las que escribe `POST /api/ventas`— da lo que dice.

🔴 `POST /api/ventas` no guarda el costo de la línea (`sale_items.unit_cost_snapshot` queda vacío): el margen sale con el costo de HOY
del producto y así lo marca (`costo_estimado`). Si algún día la venta guarda su costo, esa marca pasa a `False` y el test de abajo lo
dice.
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
    # El costo es el de hoy y lo dice: `POST /api/ventas` no guarda el de la venta.
    assert p["costo_estimado"] is True and m["resumen"]["productos_costo_estimado"] == 1


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


def test_un_cajero_no_ve_el_costo_ni_el_margen(staff_client):
    assert staff_client.get("/api/reportes/margen").status_code == 403
    assert staff_client.get("/api/reportes/margen/export/productos").status_code == 403
    assert staff_client.get("/api/reportes/margen/export/periodos").status_code == 403


def test_sin_decision_de_plan_esta_disponible_para_todo_admin(admin_client):
    """🔴 Documenta una decisión PENDIENTE, no la toma: en qué plan cae el margen no lo decidió el humano (`plans.py` anticipa
    "Premium con margen para reportes"). Hoy no hay `require_module` sobre esta ruta, igual que Reportes. Cuando se decida gatearla,
    este test cambia junto con `plans.py` y el `dependencies=` de `main.py`."""
    for modulo in ("facturacion", "dashboard"):
        admin_client.app.state.modules.set_enabled(modulo, False)
    assert admin_client.get("/api/reportes/margen").status_code == 200
