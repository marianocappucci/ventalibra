"""Los proveedores son el router del motor (`libracore.egresos_router`, `/api/proveedores`), el mismo que
montan Contalibra y Restolibra (ADR-030). Acá se prueba **el montaje en VentaLibra**: el contrato que
necesitan la pantalla del kit y Compras, y la guarda de baja con compras.
"""
from ventas_helpers import crear_item

from app.services.proveedores import OFFSET_PROVEEDOR


def test_crear_listar_y_leer_un_proveedor(admin_client):
    creado = admin_client.post("/api/proveedores", json={
        "nombre": "Distribuidora SA", "cuit_dni": "30-12345678-9", "email": "ventas@ds.test",
    })
    assert creado.status_code in (200, 201), creado.text
    listado = admin_client.get("/api/proveedores").json()
    proveedor = next(p for p in listado if p["nombre"] == "Distribuidora SA")
    assert (proveedor["cuit_dni"], proveedor["email"]) == ("30-12345678-9", "ventas@ds.test")


def test_la_lista_no_incluye_a_los_clientes(admin_client):
    admin_client.post("/api/clientes", json={"name": "Ana Cliente"})
    admin_client.post("/api/proveedores", json={"nombre": "Distribuidora SA"})
    assert [p["nombre"] for p in admin_client.get("/api/proveedores").json()] == ["Distribuidora SA"]


def test_el_proveedor_nuevo_tiene_su_party_desde_el_alta(admin_client):
    """ADR-093: el party espejo (id + 100.000) nace con el proveedor y no al comprarle, porque en un nodo no se escribe: baja
    por el espejo. Editar el proveedor lo refresca sin ir a comprar."""
    proveedor_id = admin_client.post("/api/proveedores", json={"nombre": "Prov", "cuit_dni": "30-11111111-1"}).json()["id"]
    conn = admin_client.app.state.conn
    party = OFFSET_PROVEEDOR + proveedor_id
    assert tuple(conn.execute("SELECT display_name, tax_id FROM parties WHERE id = ?", (party,)).fetchone()) == (
        "Prov", "30-11111111-1")

    assert admin_client.put(f"/api/proveedores/{proveedor_id}", json={"nombre": "Prov renombrado"}).status_code == 200
    assert tuple(conn.execute("SELECT display_name, tax_id FROM parties WHERE id = ?", (party,)).fetchone()) == (
        "Prov renombrado", None)

    orden = admin_client.post("/api/purchase-orders", json={"proveedor_id": proveedor_id})
    assert orden.status_code == 200, orden.text
    assert orden.json()["proveedor_id"] == proveedor_id
    assert "supplier_party_id" not in orden.json()  # el contrato público sólo habla de `proveedor_id`


def test_un_alta_rechazada_no_toca_los_parties(admin_client):
    assert admin_client.post("/api/proveedores", json={"nombre": "  "}).status_code == 422
    conn = admin_client.app.state.conn
    assert conn.execute("SELECT COUNT(*) FROM parties WHERE id >= ?", (OFFSET_PROVEEDOR,)).fetchone()[0] == 0


def test_sincronizar_los_parties_es_idempotente_y_no_reescribe_lo_que_esta_al_dia(admin_client):
    """El backfill (migración 0010) completa a los proveedores que ya existían, y volver a correrlo no reescribe nada: si lo
    hiciera, cada sincronización dispararía el changelog de LibraEdge. `xmin` cambia con cada reescritura de la fila."""
    from app.services.proveedores import sincronizar_parties_de_proveedores

    conn = admin_client.app.state.conn
    ids = [admin_client.post("/api/proveedores", json={"nombre": f"Prov {n}"}).json()["id"] for n in range(2)]
    # Un proveedor «viejo»: creado cuando el alta no hacía el party.
    conn.execute("DELETE FROM parties WHERE id = ?", (OFFSET_PROVEEDOR + ids[0],))
    conn.commit()

    assert sincronizar_parties_de_proveedores(conn) == 2
    conn.commit()
    xmin = [tuple(f) for f in conn.execute(
        "SELECT id, xmin::text FROM parties WHERE id >= ? ORDER BY id", (OFFSET_PROVEEDOR,)).fetchall()]
    assert [f[0] for f in xmin] == [OFFSET_PROVEEDOR + i for i in ids]

    assert sincronizar_parties_de_proveedores(conn) == 2
    conn.commit()
    assert [tuple(f) for f in conn.execute(
        "SELECT id, xmin::text FROM parties WHERE id >= ? ORDER BY id", (OFFSET_PROVEEDOR,)).fetchall()] == xmin


def test_una_compra_a_un_proveedor_que_no_existe_da_404(admin_client):
    assert admin_client.post("/api/purchase-orders", json={"proveedor_id": 9999}).status_code == 404
    assert admin_client.post("/api/purchase-receipts", json={"proveedor_id": 9999}).status_code == 404


def test_el_espejo_toma_el_nombre_actual_al_comprar(admin_client):
    proveedor = admin_client.post("/api/proveedores", json={"nombre": "Viejo"}).json()
    admin_client.post("/api/purchase-orders", json={"proveedor_id": proveedor["id"]})
    admin_client.put(f"/api/proveedores/{proveedor['id']}", json={"nombre": "Nuevo nombre"})
    admin_client.post("/api/purchase-orders", json={"proveedor_id": proveedor["id"]})
    party = OFFSET_PROVEEDOR + proveedor["id"]
    conn = admin_client.app.state.conn
    assert conn.execute("SELECT display_name FROM parties WHERE id = ?", (party,)).fetchone()[0] == "Nuevo nombre"


def test_un_proveedor_con_compras_no_se_elimina(admin_client):
    """El motor sólo mira los egresos; VentaLibra guarda la baja si hay órdenes o recepciones."""
    proveedor_id = admin_client.post("/api/proveedores", json={"nombre": "Con compras"}).json()["id"]
    admin_client.post("/api/purchase-orders", json={"proveedor_id": proveedor_id})
    r = admin_client.delete(f"/api/proveedores/{proveedor_id}")
    assert r.status_code == 409, r.text
    assert "compras" in r.json()["detail"]
    assert any(p["id"] == proveedor_id for p in admin_client.get("/api/proveedores").json())


def test_un_proveedor_sin_compras_se_elimina(admin_client):
    proveedor_id = admin_client.post("/api/proveedores", json={"nombre": "Sin compras"}).json()["id"]
    assert admin_client.delete(f"/api/proveedores/{proveedor_id}").status_code in (200, 204)
    assert admin_client.get("/api/proveedores").json() == []


def test_el_deposito_puede_ver_los_proveedores(deposito_client):
    assert deposito_client.get("/api/proveedores").status_code == 200
