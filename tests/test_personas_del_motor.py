"""Clientes y proveedores sobre el modelo del motor (migración `0004`, 2026-09-26): la convención
de ids de Contalibra -- cliente = party de igual id; proveedor = party con id `proveedores.id +
100.000`--, que es lo que permite retirar los puentes `cliente_cc_de` / `nombre_de_cliente`.
"""
import test_cuenta_corriente as cc
from ventas_helpers import abrir_turno, crear_item


def _conn(client):
    return client.app.state.conn


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
