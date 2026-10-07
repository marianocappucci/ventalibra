"""Egresos (fase 11 de la adopción de los motores, 2026-09-27, ADR-038): el router del motor
(`libracore.egresos_router.build_egresos_router`), montado tal cual -- no tiene opciones que enganchar.
Complementa a Compras: Compras repone inventario, Egresos es la contabilidad del pago (alquiler,
sueldos, servicios, y también un pago a proveedor que Compras no cubre). De encargado y admin, libre en
todos los planes de este producto.
"""


def _crear_proveedor(client, nombre="Distribuidora SA") -> int:
    r = client.post("/api/proveedores", json={"nombre": nombre})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _crear_egreso(client, concepto="Alquiler septiembre", monto_neto=1000, iva_pct=0.21, **extra):
    r = client.post("/api/egresos", json={
        "concepto": concepto, "monto_neto": monto_neto, "iva_pct": iva_pct, **extra,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_crear_un_egreso_calcula_iva_y_total(admin_client):
    egreso = _crear_egreso(admin_client, monto_neto=1000, iva_pct=0.21)
    assert egreso["iva_monto"] == 210 and egreso["total"] == 1210 and egreso["estado"] == "pendiente"


def test_el_concepto_es_obligatorio_y_el_total_no_puede_ser_cero(admin_client):
    assert admin_client.post("/api/egresos", json={"concepto": "  "}).status_code == 422
    assert admin_client.post("/api/egresos", json={"concepto": "X", "monto_neto": 0}).status_code == 422


def test_un_egreso_con_proveedor_guarda_su_nombre(admin_client):
    proveedor = _crear_proveedor(admin_client)
    egreso = _crear_egreso(admin_client, proveedor_id=proveedor)
    assert egreso["proveedor_id"] == proveedor and egreso["proveedor_nombre"] == "Distribuidora SA"


def test_categorias_de_egreso(admin_client):
    """La instancia arranca con categorías precargadas (el motor las siembra); acá se prueba sólo lo que
    agrega este alta: que quede la nueva y que borrarla la saque, sin asumir una lista vacía."""
    iniciales = {c["nombre"] for c in admin_client.get("/api/egresos/categorias").json()}
    assert "Fletes propios" not in iniciales

    creada = admin_client.post("/api/egresos/categorias", json={"nombre": "Fletes propios"})
    assert creada.status_code == 200
    con_nueva = {c["nombre"]: c["id"] for c in creada.json()}
    assert con_nueva.keys() == iniciales | {"Fletes propios"}

    tras_borrar = admin_client.delete(f"/api/egresos/categorias/{con_nueva['Fletes propios']}")
    assert {c["nombre"] for c in tras_borrar.json()} == iniciales
    assert admin_client.post("/api/egresos/categorias", json={"nombre": " "}).status_code == 422


def test_listar_trae_el_resumen_del_periodo(admin_client):
    _crear_egreso(admin_client, monto_neto=1000, iva_pct=0)
    _crear_egreso(admin_client, monto_neto=500, iva_pct=0)
    listado = admin_client.get("/api/egresos")
    assert listado.status_code == 200
    data = listado.json()
    assert len(data["items"]) == 2
    assert data["resumen"] == {"total_periodo": 1500, "pagado": 0, "pendiente": 1500}


def test_pagar_un_egreso_crea_el_movimiento_de_caja_y_actualiza_el_estado(admin_client):
    egreso = _crear_egreso(admin_client, monto_neto=1000, iva_pct=0)
    parcial = admin_client.post(f"/api/egresos/{egreso['id']}/pagar", json={
        "monto": 400, "medio_pago": "efectivo", "fecha": "2026-09-27",
    })
    assert parcial.status_code == 200 and parcial.json()["estado"] == "parcial"

    # Sin `monto` no paga "lo que falta": paga el `total` del egreso de nuevo (así lo resuelve el motor).
    completo = admin_client.post(f"/api/egresos/{egreso['id']}/pagar", json={
        "monto": 600, "medio_pago": "efectivo", "fecha": "2026-09-27",
    })
    assert completo.status_code == 200 and completo.json()["estado"] == "pagado"

    pagos = admin_client.get(f"/api/egresos/{egreso['id']}/pagos")
    assert pagos.status_code == 200 and len(pagos.json()) == 2
    assert sum(p["monto"] for p in pagos.json()) == 1000


def test_pagar_un_egreso_inexistente_da_404(admin_client):
    assert admin_client.post("/api/egresos/999/pagar", json={"medio_pago": "efectivo"}).status_code == 404
    assert admin_client.get("/api/egresos/999/pagos").status_code == 404


def test_eliminar_un_egreso(admin_client):
    egreso = _crear_egreso(admin_client)
    assert admin_client.delete(f"/api/egresos/{egreso['id']}").status_code == 200
    assert admin_client.get("/api/egresos").json()["items"] == []


def test_un_proveedor_con_egresos_no_se_elimina(admin_client):
    """La guarda del motor (`ValueError` -> 422 en `build_proveedores_router`), recién activa desde esta
    fase: antes de adoptar Egresos, VentaLibra no tenía cómo dejar a un proveedor con esa deuda."""
    proveedor = _crear_proveedor(admin_client)
    _crear_egreso(admin_client, proveedor_id=proveedor)
    r = admin_client.delete(f"/api/proveedores/{proveedor}")
    assert r.status_code == 422 and "egresos" in r.json()["detail"]


def test_un_cajero_puede_usar_egresos_libre_de_gate_de_plan(encargado_client):
    """Egresos es de encargado y admin (ADR-038), a diferencia de Tesorería que es sólo de admin."""
    egreso = _crear_egreso(encargado_client, monto_neto=100, iva_pct=0)
    assert encargado_client.get("/api/egresos").status_code == 200
    assert encargado_client.post(f"/api/egresos/{egreso['id']}/pagar", json={"medio_pago": "efectivo"}).status_code == 200
