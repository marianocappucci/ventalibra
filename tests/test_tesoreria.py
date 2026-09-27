"""Tesorería (fase 10 de la adopción de los motores, 2026-09-27, ADR-037): el router del motor
(`libracore.tesoreria_router.build_tesoreria_router`), montado tal cual -- no tiene opciones que
enganchar. Cuentas bancarias, efectivo y billeteras digitales, con sus movimientos y transferencias
entre cuentas; libre en todos los planes de este producto (a diferencia de Contalibra, donde es un
módulo de plan "estándar") y de admin, mismo criterio que Cajas y Listas de precio.
"""


def _crear_cuenta(client, nombre="Banco Galicia", tipo="banco", saldo_inicial=0):
    r = client.post("/api/tesoreria/cuentas", json={
        "nombre": nombre, "tipo": tipo, "banco": "Galicia", "numero": "1234",
        "descripcion": "Cuenta corriente", "saldo_inicial": saldo_inicial,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_crear_cuenta_y_verla_en_el_resumen(admin_client):
    cuenta = _crear_cuenta(admin_client, saldo_inicial=1000)
    assert cuenta["nombre"] == "Banco Galicia" and cuenta["saldo"] == 1000

    resumen = admin_client.get("/api/tesoreria")
    assert resumen.status_code == 200, resumen.text
    data = resumen.json()
    assert any(c["id"] == cuenta["id"] for c in data["cuentas"])
    assert data["movimientos"] == []
    assert data["resumen"]["total"] == 1000


def test_el_nombre_es_obligatorio(admin_client):
    r = admin_client.post("/api/tesoreria/cuentas", json={"nombre": "  "})
    assert r.status_code == 422


def test_actualizar_y_archivar_una_cuenta(admin_client):
    cuenta = _crear_cuenta(admin_client)
    editada = admin_client.put(f"/api/tesoreria/cuentas/{cuenta['id']}", json={
        "nombre": "Banco Galicia SA", "tipo": "banco", "saldo_inicial": 0,
    })
    assert editada.status_code == 200 and editada.json()["nombre"] == "Banco Galicia SA"

    # "Eliminar" archiva (`activa=0`), no borra: sigue en el detalle pero sale del resumen general.
    assert admin_client.delete(f"/api/tesoreria/cuentas/{cuenta['id']}").status_code == 200
    detalle = admin_client.get(f"/api/tesoreria/cuentas/{cuenta['id']}")
    assert detalle.status_code == 200 and detalle.json()["cuenta"]["activa"] == 0
    assert cuenta["id"] not in {c["id"] for c in admin_client.get("/api/tesoreria").json()["cuentas"]}

    assert admin_client.put("/api/tesoreria/cuentas/999", json={"nombre": "X"}).status_code == 404
    assert admin_client.delete("/api/tesoreria/cuentas/999").status_code == 404


def test_un_movimiento_actualiza_el_saldo_y_queda_en_el_detalle(admin_client):
    cuenta = _crear_cuenta(admin_client, saldo_inicial=500)
    ingreso = admin_client.post(f"/api/tesoreria/cuentas/{cuenta['id']}/movimiento", json={
        "tipo": "ingreso", "monto": 200, "concepto": "Depósito", "fecha": "2026-09-27",
    })
    assert ingreso.status_code == 200 and ingreso.json()["saldo"] == 700

    egreso = admin_client.post(f"/api/tesoreria/cuentas/{cuenta['id']}/movimiento", json={
        "tipo": "egreso", "monto": 100, "concepto": "Retiro", "fecha": "2026-09-27",
    })
    assert egreso.status_code == 200 and egreso.json()["saldo"] == 600

    detalle = admin_client.get(f"/api/tesoreria/cuentas/{cuenta['id']}")
    assert detalle.status_code == 200
    conceptos = [m["concepto"] for m in detalle.json()["movimientos"]]
    assert set(conceptos) == {"Depósito", "Retiro"}


def test_un_movimiento_de_monto_invalido_o_sin_concepto_da_422(admin_client):
    cuenta = _crear_cuenta(admin_client)
    sin_concepto = admin_client.post(f"/api/tesoreria/cuentas/{cuenta['id']}/movimiento", json={
        "tipo": "ingreso", "monto": 100, "concepto": "  ", "fecha": "2026-09-27",
    })
    assert sin_concepto.status_code == 422
    monto_cero = admin_client.post(f"/api/tesoreria/cuentas/{cuenta['id']}/movimiento", json={
        "tipo": "ingreso", "monto": 0, "concepto": "Depósito", "fecha": "2026-09-27",
    })
    assert monto_cero.status_code == 422


def test_una_transferencia_mueve_plata_entre_las_dos_cuentas(admin_client):
    origen = _crear_cuenta(admin_client, nombre="Efectivo", tipo="efectivo", saldo_inicial=1000)
    destino = _crear_cuenta(admin_client, nombre="MercadoPago", tipo="digital")

    r = admin_client.post("/api/tesoreria/transferencia", json={
        "cuenta_origen_id": origen["id"], "cuenta_destino_id": destino["id"],
        "monto": 300, "fecha": "2026-09-27",
    })
    assert r.status_code == 200, r.text

    assert admin_client.get(f"/api/tesoreria/cuentas/{origen['id']}").json()["cuenta"]["saldo"] == 700
    assert admin_client.get(f"/api/tesoreria/cuentas/{destino['id']}").json()["cuenta"]["saldo"] == 300


def test_transferir_a_la_misma_cuenta_o_a_una_inexistente_falla(admin_client):
    cuenta = _crear_cuenta(admin_client, saldo_inicial=1000)
    misma = admin_client.post("/api/tesoreria/transferencia", json={
        "cuenta_origen_id": cuenta["id"], "cuenta_destino_id": cuenta["id"], "monto": 100, "fecha": "2026-09-27",
    })
    assert misma.status_code == 422

    inexistente = admin_client.post("/api/tesoreria/transferencia", json={
        "cuenta_origen_id": cuenta["id"], "cuenta_destino_id": 999, "monto": 100, "fecha": "2026-09-27",
    })
    assert inexistente.status_code == 404


def test_eliminar_un_movimiento(admin_client):
    cuenta = _crear_cuenta(admin_client)
    admin_client.post(f"/api/tesoreria/cuentas/{cuenta['id']}/movimiento", json={
        "tipo": "ingreso", "monto": 100, "concepto": "Depósito", "fecha": "2026-09-27",
    })
    mov_id = admin_client.get(f"/api/tesoreria/cuentas/{cuenta['id']}").json()["movimientos"][0]["id"]
    assert admin_client.delete(f"/api/tesoreria/movimientos/{mov_id}").status_code == 200
    assert admin_client.get(f"/api/tesoreria/cuentas/{cuenta['id']}").json()["cuenta"]["saldo"] == 0


def test_un_cajero_no_entra_libre_en_todos_los_planes(admin_client, staff_client):
    """La decisión (ADR-037) es que Tesorería queda libre de gate de plan, pero sigue siendo de admin:
    un cajero (staff) no puede ni leerla ni escribirla."""
    cuenta = _crear_cuenta(admin_client)
    assert staff_client.get("/api/tesoreria").status_code == 403
    assert staff_client.post("/api/tesoreria/cuentas", json={"nombre": "X"}).status_code == 403
    assert staff_client.post(f"/api/tesoreria/cuentas/{cuenta['id']}/movimiento", json={
        "tipo": "ingreso", "monto": 100, "concepto": "X", "fecha": "2026-09-27",
    }).status_code == 403
