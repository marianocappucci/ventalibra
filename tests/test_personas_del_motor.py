"""Clientes y proveedores sobre el modelo del motor (migración `0004`, 2026-09-26): la convención
de ids de Contalibra -- cliente = party de igual id; proveedor = party con id `proveedores.id +
100.000`--, que es lo que permite retirar los puentes `cliente_cc_de` / `nombre_de_cliente`.
"""
import test_cuenta_corriente as cc
from ventas_helpers import abrir_turno, crear_item

from app.services.suppliers import OFFSET_PROVEEDOR


def _conn(client):
    return client.app.state.conn


def test_un_cliente_nuevo_es_a_la_vez_el_client_y_el_party_de_igual_id(admin_client):
    r = admin_client.post("/customers", json={
        "display_name": "Kiosco Norte", "cuit": "30-71888999-2", "condicion_iva": "Responsable Inscripto",
    })
    assert r.status_code == 200, r.text
    cliente = r.json()
    conn = _conn(admin_client)
    fila = conn.execute(
        "SELECT name, cuit_dni, iva_condition, activo FROM clients WHERE id = ?", (cliente["id"],)
    ).fetchone()
    assert tuple(fila) == ("Kiosco Norte", "30-71888999-2", "Responsable Inscripto", 1)
    party = conn.execute("SELECT display_name FROM parties WHERE id = ?", (cliente["id"],)).fetchone()
    assert party[0] == "Kiosco Norte"
    assert (cliente["cuit"], cliente["condicion_iva"], cliente["active"]) == (
        "30-71888999-2", "Responsable Inscripto", True)


def test_un_cuit_repetido_da_409_como_en_el_motor(admin_client):
    body = {"display_name": "Uno", "cuit": "30-71222333-4"}
    assert admin_client.post("/customers", json=body).status_code == 200
    r = admin_client.post("/customers", json={**body, "display_name": "Dos"})
    assert r.status_code == 409, r.text


def test_la_venta_fiada_llega_a_la_cuenta_por_el_mismo_id(admin_client):
    """Sin traducción: el `cliente_id` que manda el POS es el de `clients`, y la cuenta corriente
    y la venta lo cruzan por id."""
    item_id = crear_item(admin_client)
    cliente_id = cc._make_cliente(admin_client)
    abrir_turno(admin_client)
    cc._venta_fiada(admin_client, cliente_id, item_id)

    cuenta = admin_client.get(f"/accounts/{cliente_id}").json()
    assert float(cuenta["saldo"]) == 3000
    deudores = admin_client.get("/accounts").json()
    assert [d["party_id"] for d in deudores] == [cliente_id]
    # La venta quedó atada al mismo id, sin pasar por `external_ref`.
    assert _conn(admin_client).execute(
        "SELECT customer_party_id FROM sales WHERE customer_party_id IS NOT NULL"
    ).fetchone()[0] == cliente_id


def test_un_proveedor_nuevo_es_el_proveedor_y_el_party_con_offset(admin_client):
    r = admin_client.post("/suppliers", json={
        "display_name": "Distribuidora Sur", "tax_id": "30-70111222-3", "email": "ventas@sur.test",
    })
    assert r.status_code == 200, r.text
    proveedor = r.json()
    conn = _conn(admin_client)
    fila = conn.execute("SELECT id, nombre, cuit_dni FROM proveedores").fetchone()
    assert proveedor["id"] == OFFSET_PROVEEDOR + fila[0]
    assert (fila[1], fila[2]) == ("Distribuidora Sur", "30-70111222-3")
    party = conn.execute("SELECT display_name FROM parties WHERE id = ?", (proveedor["id"],)).fetchone()
    assert party[0] == "Distribuidora Sur"
    # Se lista y se lee por el id del party (el contrato de `/suppliers` y de Compras).
    assert [p["id"] for p in admin_client.get("/suppliers").json()] == [proveedor["id"]]
    assert admin_client.get(f"/suppliers/{proveedor['id']}").json()["display_name"] == "Distribuidora Sur"
    assert admin_client.get("/suppliers/1").status_code == 404


def test_una_orden_de_compra_acepta_al_proveedor_nuevo(admin_client):
    proveedor = admin_client.post("/suppliers", json={"display_name": "Prov"}).json()
    r = admin_client.post("/purchase-orders", json={"supplier_party_id": proveedor["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["supplier_party_id"] == proveedor["id"]
