"""Dashboard con el router del motor (`/api/dashboard`, fase 13, ADR-039).

`libracore.dashboard_router.build_dashboard_router`, el mismo que Contalibra, con `sin_fiado=True`
(libracore v1.114.0): una venta a cuenta corriente no es plata en el cajón, mismo criterio que Reportes
(fase 8). Estuvo gateado a Premium (ADR-039) y **desde ADR-048 es libre en los dos planes**: lo que distingue un
plan es la facturación y la multisucursal, no el tablero. De admin.
"""
from ventas_helpers import caja_default, registrar_venta


def _abrir_turno(client, monto_inicial=0):
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


def test_por_default_el_tablero_esta_disponible_para_el_admin(admin_client):
    r = admin_client.get("/api/dashboard")
    assert r.status_code == 200, r.text
    assert r.json()["facturado_mes"] == 0 and r.json()["ultimos_movimientos"] == []


def test_fiar_no_es_cobrar_en_el_tablero(admin_client):
    """La capa ERP escribe un movimiento de caja por cada medio, cuenta corriente incluido. Sin
    `sin_fiado` el tablero sumaría la deuda como plata en el cajón."""
    item_id = _make_item(admin_client, price="1000.00")
    cliente = admin_client.post("/api/clientes", json={"name": "Kiosco"}).json()["id"]
    _abrir_turno(admin_client)
    registrar_venta(admin_client, item_id, precio="1000.00", cantidad="1")  # efectivo: 1000
    registrar_venta(admin_client, item_id, precio="2000.00", cantidad="1", cliente_id=cliente,
                    pagos=[{"medio": "cuenta_corriente", "monto": 2000.0}])

    d = admin_client.get("/api/dashboard").json()
    assert d["cobrado_mes"] == 1000.0  # sólo la venta en efectivo entró al cajón
    assert d["saldo_total"] == 1000.0
    assert [m["medio_pago"] for m in d["ultimos_movimientos"]] == ["efectivo"]


def test_sin_ningun_modulo_el_tablero_se_abre(admin_client):
    """ADR-048: el dashboard ya no es de ningún plan. Con todos los módulos apagados (Básico) sigue libre; la
    versión vieja de este test (`set_enabled("dashboard", False)` -> 403) se retiró junto con el gate."""
    for modulo in ("facturacion", "multisucursal"):
        admin_client.app.state.modules.set_enabled(modulo, False)
    assert admin_client.get("/api/dashboard").status_code == 200


def test_un_cajero_no_ve_el_tablero(staff_client):
    assert staff_client.get("/api/dashboard").status_code == 403
