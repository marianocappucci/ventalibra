"""Los clientes son el router del motor (`libracore.clientes_router`, `/api/clientes`), el mismo que
montan Contalibra y Restolibra (ADR-029). Acá se prueba **el montaje en VentaLibra**: el contrato que
necesitan el POS y la pantalla del kit, y la convención de ids de la `0004` (cliente = party).
"""


def test_crear_un_cliente_sin_datos_de_facturacion(admin_client):
    creado = admin_client.post("/api/clientes", json={"name": "Juan Perez"})
    assert creado.status_code == 200, creado.text
    assert creado.json()["cuit_dni"] in (None, "")
    assert creado.json()["activo"] == 1


def test_crear_un_cliente_con_datos_de_facturacion(admin_client):
    creado = admin_client.post("/api/clientes", json={
        "name": "Ana Gomez", "cuit_dni": "27-12345678-9", "iva_condition": "Responsable Inscripto",
        "email": "ana@example.com.ar", "phone": "11 5555-0000",
    })
    assert creado.status_code == 200, creado.text
    cliente_id = creado.json()["id"]

    ficha = admin_client.get(f"/api/clientes/{cliente_id}")
    assert ficha.status_code == 200
    cuerpo = ficha.json()
    assert (cuerpo["cuit_dni"], cuerpo["iva_condition"]) == ("27-12345678-9", "Responsable Inscripto")
    # La ficha del kit espera estas claves aunque VentaLibra no muestre esos módulos.
    assert {"alias_facturacion", "facturas", "presupuestos", "remitos"} <= set(cuerpo)
    assert any(c["id"] == cliente_id for c in admin_client.get("/api/clientes").json())


def test_un_cliente_que_no_existe_da_404(admin_client):
    assert admin_client.get("/api/clientes/999").status_code == 404


def test_la_lista_no_incluye_a_los_proveedores(admin_client):
    admin_client.post("/suppliers", json={"display_name": "Distribuidora SA"})
    cliente = admin_client.post("/api/clientes", json={"name": "Ana Cliente"}).json()

    assert [c["id"] for c in admin_client.get("/api/clientes").json()] == [cliente["id"]]


def test_un_cuit_repetido_da_422_como_en_el_motor(admin_client):
    cuerpo = {"name": "Uno", "cuit_dni": "30-71222333-4"}
    assert admin_client.post("/api/clientes", json=cuerpo).status_code == 200
    r = admin_client.post("/api/clientes", json={**cuerpo, "name": "Dos"})
    assert r.status_code == 422, r.text


def test_desactivar_y_reactivar_un_cliente(admin_client):
    cliente_id = admin_client.post("/api/clientes", json={"name": "Baja"}).json()["id"]
    assert admin_client.post(f"/api/clientes/{cliente_id}/desactivar").json()["activo"] == 0
    # El listado del motor incluye a los inactivos (la pantalla los marca); el POS filtra por `activo`.
    assert [c["activo"] for c in admin_client.get("/api/clientes").json()] == [0]
    assert admin_client.post(f"/api/clientes/{cliente_id}/activar").json()["activo"] == 1


def test_un_cajero_puede_dar_de_alta_un_cliente(staff_client):
    """El POS da de alta clientes al vuelo: staff o admin, como el resto del mostrador."""
    r = staff_client.post("/api/clientes", json={"name": "Del cajero"})
    assert r.status_code == 200, r.text


def test_el_cliente_nuevo_es_a_la_vez_el_party_de_igual_id(admin_client):
    """La convención de la `0004`: la venta y la cuenta corriente cruzan por id sin traducir."""
    cliente_id = admin_client.post("/api/clientes", json={"name": "Kiosco Norte"}).json()["id"]
    conn = admin_client.app.state.conn
    assert conn.execute("SELECT display_name FROM parties WHERE id = ?", (cliente_id,)).fetchone()[0] == "Kiosco Norte"
