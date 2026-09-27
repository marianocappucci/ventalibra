"""Libros IVA (fase 12 de la adopción de los motores, 2026-09-27, ADR-038): el router del motor
(`libracore.libros_iva_router`), montado tal cual. El lado ventas ya funcionaba (las facturas son la
tabla `facturas` del motor, que este producto escribe desde `venta_facturacion`); el lado compras se
completa con Egresos (fase 11, en la misma tanda). De admin: es un reporte contable-fiscal, no una tarea
de mostrador -- a diferencia de Egresos, acá si se sigue el criterio de Contalibra al pie de la letra.
"""


def _crear_egreso_factura(client, monto_neto=1000, iva_pct=0.21, fecha="2026-09-15", proveedor_id=None):
    r = client.post("/api/egresos", json={
        "concepto": "Compra de insumos", "monto_neto": monto_neto, "iva_pct": iva_pct,
        "fecha": fecha, "tipo_comprobante": "factura", "numero": "0001-00000042",
        "proveedor_id": proveedor_id,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_sin_facturas_ni_egresos_el_resumen_da_todo_en_cero(admin_client):
    r = admin_client.get("/api/libros-iva")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["facturas"] == [] and data["egresos"] == []
    assert data["resumen_v"] == {"cbtes": 0, "neto": 0, "iva": 0, "total": 0, "por_tasa": {}}
    assert data["resumen_c"] == {"cbtes": 0, "neto": 0, "iva": 0, "total": 0, "por_tasa": {}}
    # Sin desde/hasta, el período por defecto es el mes en curso.
    assert data["desde"] and data["hasta"]


def test_un_egreso_tipo_factura_entra_al_libro_de_compras(admin_client):
    proveedor = admin_client.post("/api/proveedores", json={"nombre": "Insumos SA", "cuit_dni": "30-1"}).json()
    egreso = _crear_egreso_factura(admin_client, monto_neto=1000, iva_pct=0.21, proveedor_id=proveedor["id"])

    r = admin_client.get("/api/libros-iva", params={"desde": "2026-09-01", "hasta": "2026-09-30"})
    data = r.json()
    assert len(data["egresos"]) == 1
    fila = data["egresos"][0]
    assert fila["id"] == egreso["id"] and fila["proveedor_cuit"] == "30-1"
    # `_alicuota_de_egreso` deriva la tasa del importe, en PUNTOS (21.0, no 0.21) -- no lee `iva_pct`.
    assert data["resumen_c"] == {"cbtes": 1, "neto": 1000, "iva": 210, "total": 1210, "por_tasa": {"21.0": {"neto": 1000, "iva": 210, "cbtes": 1}}}


def test_un_egreso_que_no_es_factura_no_entra_al_libro(admin_client):
    admin_client.post("/api/egresos", json={
        "concepto": "Café de la oficina", "monto_neto": 50, "tipo_comprobante": "ticket",
        "fecha": "2026-09-15",
    })
    r = admin_client.get("/api/libros-iva", params={"desde": "2026-09-01", "hasta": "2026-09-30"})
    assert r.json()["egresos"] == []


def test_fuera_del_periodo_no_entra(admin_client):
    _crear_egreso_factura(admin_client, fecha="2026-08-15")
    r = admin_client.get("/api/libros-iva", params={"desde": "2026-09-01", "hasta": "2026-09-30"})
    assert r.json()["egresos"] == []


def test_un_cajero_no_ve_libros_iva(staff_client):
    assert staff_client.get("/api/libros-iva").status_code == 403


def test_los_cuatro_exports_reginfo(admin_client):
    for ruta, prefijo in [
        ("ventas-cbte", "REGINFO_CV_VENTAS_CBTE_"),
        ("ventas-alicuotas", "REGINFO_CV_VENTAS_ALICUOTAS_"),
        ("compras-cbte", "REGINFO_CV_COMPRAS_CBTE_"),
        ("compras-alicuotas", "REGINFO_CV_COMPRAS_ALICUOTAS_"),
    ]:
        r = admin_client.get(f"/libros-iva/export/{ruta}", params={"desde": "2026-09-01", "hasta": "2026-09-30"})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/plain")
        assert prefijo + "202609.txt" in r.headers["content-disposition"]


def test_los_exports_son_de_admin(staff_client):
    assert staff_client.get("/libros-iva/export/ventas-cbte").status_code == 403
