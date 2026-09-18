"""La venta y la devolución salen del depósito de la sucursal de la caja del turno.

🔴 Hasta el 2026-09-17 esto lo garantizaba sólo el POS (fija la sucursal a la de
la caja apenas hay turno). Por la API se podía vender desde la caja de un local
descontando el stock del otro. Ahora lo valida el backend con el gancho
`validar_deposito` de libracommerce v0.17.0 (`app/ganchos.py`): 422 y nada
escrito.
"""
from test_cajas import _cajas_de, _crear_sucursal
from ventas_helpers import (
    abrir_turno,
    caja_default,
    con_stock,
    crear_item,
    deposito_default,
    primer_sale_item_id,
    registrar_venta,
    stock,
)


def _conteos(client) -> tuple:
    conn = client.app.state.conn
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in ("sales", "ventas_pagos", "caja_movimientos", "stock_movements")
    )


def _otra_sucursal_con_turno(admin_client, staff_client):
    """Una segunda sucursal con stock y un turno del staff abierto en su caja."""
    sucursal2 = _crear_sucursal(admin_client)
    caja2 = _cajas_de(admin_client, sucursal2["id"])[0]["id"]
    abrir_turno(staff_client, caja_id=caja2)
    return sucursal2["id"]


def test_vender_desde_otra_sucursal_da_422_y_no_escribe_nada(admin_client, staff_client):
    item_id = crear_item(admin_client)
    principal = deposito_default(admin_client)
    sucursal2 = _otra_sucursal_con_turno(admin_client, staff_client)
    con_stock(admin_client, item_id, principal)
    con_stock(admin_client, item_id, sucursal2)
    antes = _conteos(admin_client)

    error = registrar_venta(staff_client, item_id, cantidad="1", deposito_id=principal, esperar=422)

    assert "sucursal" in error["detail"]
    assert _conteos(admin_client) == antes
    assert stock(admin_client, item_id, principal) == 20


def test_sin_deposito_se_valida_contra_el_default(admin_client, staff_client):
    """Sin `deposito_id` el motor descuenta del default: si el default es de
    otra sucursal que la de la caja, también se rechaza."""
    item_id = crear_item(admin_client)
    con_stock(admin_client, item_id, deposito_default(admin_client))
    _otra_sucursal_con_turno(admin_client, staff_client)
    antes = _conteos(admin_client)

    registrar_venta(staff_client, item_id, cantidad="1", esperar=422)

    assert _conteos(admin_client) == antes


def test_vender_desde_la_sucursal_de_la_caja_se_registra(admin_client, staff_client):
    item_id = crear_item(admin_client)
    sucursal2 = _otra_sucursal_con_turno(admin_client, staff_client)
    con_stock(admin_client, item_id, sucursal2)

    registrar_venta(staff_client, item_id, cantidad="2", deposito_id=sucursal2)

    assert stock(admin_client, item_id, sucursal2) == 18


def test_sin_deposito_en_la_sucursal_default_se_sigue_registrando(admin_client):
    """El caso de todo cliente con un solo local: caja de la sucursal default y
    venta sin `deposito_id`. No cambia nada."""
    item_id = crear_item(admin_client)
    principal = deposito_default(admin_client)
    con_stock(admin_client, item_id, principal)
    abrir_turno(admin_client, caja_id=caja_default(admin_client))

    registrar_venta(admin_client, item_id, cantidad="1")

    assert stock(admin_client, item_id, principal) == 19


def test_devolver_a_otra_sucursal_da_422_y_no_repone(admin_client, staff_client):
    item_id = crear_item(admin_client)
    principal = deposito_default(admin_client)
    con_stock(admin_client, item_id, principal)
    abrir_turno(admin_client, caja_id=caja_default(admin_client))
    venta = registrar_venta(admin_client, item_id, cantidad="3", deposito_id=principal)
    sale_id = venta["id"]
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    sucursal2 = _otra_sucursal_con_turno(admin_client, staff_client)
    antes = _conteos(admin_client)

    rechazada = staff_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 1}], "deposito_id": principal,
    })
    assert rechazada.status_code == 422, rechazada.text
    assert _conteos(admin_client) == antes
    assert stock(admin_client, item_id, principal) == 17

    aceptada = staff_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 1}], "deposito_id": sucursal2,
    })
    assert aceptada.status_code == 200, aceptada.text
    assert stock(admin_client, item_id, sucursal2) == 1


def test_turno_en_una_caja_sin_sucursal_no_valida(admin_client, staff_client):
    """Datos de antes de las cajas por sucursal: una caja sin `sucursal_id` no
    tiene contra qué comparar y la venta sigue como siempre."""
    item_id = crear_item(admin_client)
    sucursal2 = _crear_sucursal(admin_client)["id"]
    con_stock(admin_client, item_id, sucursal2)
    caja_id = caja_default(admin_client)
    conn = admin_client.app.state.conn
    conn.execute("UPDATE cajas SET sucursal_id = NULL WHERE id = ?", (caja_id,))
    conn.commit()
    abrir_turno(admin_client, caja_id=caja_id)

    registrar_venta(admin_client, item_id, cantidad="1", deposito_id=sucursal2)

    assert stock(admin_client, item_id, sucursal2) == 19
