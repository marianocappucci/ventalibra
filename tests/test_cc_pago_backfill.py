"""El backfill de `caja_movimientos.cc_pago_id` (migración `0008`, `app/cc_pago_backfill.py`).

Los pagos a cuenta que VentaLibra registró antes de `libracore` v1.117.0 no tienen `cc_pago_id` en su movimiento
de caja, pero sí la referencia `cc-pago-<id>`. Sin el backfill, la baja del motor (que anula por `cc_pago_id`) no
los encuentra. El estado «viejo» se fabrica a mano sobre la base de una app ya arrancada.
"""
from test_cuenta_corriente_kit import _deudor_con_pago

from app.cc_pago_backfill import backfill_cc_pago_id


def _movimiento(conn, referencia, *, cc_pago_id=None, anulado=0) -> int:
    conn.execute(
        "INSERT INTO caja_movimientos (fecha, tipo, concepto, monto, referencia, medio_pago, cc_pago_id, anulado) "
        "VALUES ('2026-09-01', 'ingreso', 'Pago CC - x', 100, ?, 'efectivo', ?, ?)",
        (referencia, cc_pago_id, anulado),
    )
    return conn.execute("SELECT MAX(id) FROM caja_movimientos").fetchone()[0]


def _cc_pago_de(conn, mov_id):
    return conn.execute("SELECT cc_pago_id FROM caja_movimientos WHERE id = ?", (mov_id,)).fetchone()[0]


def _pago(conn, cliente_id) -> int:
    conn.execute("INSERT INTO cc_pagos (cliente_id, monto, fecha) VALUES (?, 100, '2026-09-01')", (cliente_id,))
    return conn.execute("SELECT MAX(id) FROM cc_pagos").fetchone()[0]


def _cliente(conn) -> int:
    conn.execute("INSERT INTO clients (name) VALUES ('Vecina del backfill')")
    return conn.execute("SELECT MAX(id) FROM clients").fetchone()[0]


def test_liga_el_movimiento_con_su_pago_por_la_referencia(admin_client):
    conn = admin_client.app.state.conn
    pago = _pago(conn, _cliente(conn))
    mov = _movimiento(conn, f"cc-pago-{pago}")

    assert backfill_cc_pago_id(conn) == {"ligados": 1, "huerfanos": 0}
    assert _cc_pago_de(conn, mov) == pago


def test_no_toca_lo_que_no_puede_afirmar(admin_client):
    conn = admin_client.app.state.conn
    pago = _pago(conn, _cliente(conn))
    con_sufijo = _movimiento(conn, f"cc-pago-{pago}x")
    sin_numero = _movimiento(conn, "cc-pago-")
    del_usuario = _movimiento(conn, "Transferencia nro. 2348")
    ya_ligado = _movimiento(conn, f"cc-pago-{pago}", cc_pago_id=pago + 1000)

    assert backfill_cc_pago_id(conn) == {"ligados": 0, "huerfanos": 0}
    assert [_cc_pago_de(conn, m) for m in (con_sufijo, sin_numero, del_usuario)] == [None, None, None]
    assert _cc_pago_de(conn, ya_ligado) == pago + 1000            # no pisa un vínculo que ya existe


def test_un_pago_que_ya_no_existe_no_se_inventa(admin_client):
    conn = admin_client.app.state.conn
    mov = _movimiento(conn, "cc-pago-987654", anulado=1)

    assert backfill_cc_pago_id(conn) == {"ligados": 0, "huerfanos": 1}
    assert _cc_pago_de(conn, mov) is None


def test_es_idempotente_y_no_cambia_montos_ni_anulados(admin_client):
    conn = admin_client.app.state.conn
    pago = _pago(conn, _cliente(conn))
    mov = _movimiento(conn, f"cc-pago-{pago}", anulado=1)

    backfill_cc_pago_id(conn)
    assert backfill_cc_pago_id(conn) == {"ligados": 0, "huerfanos": 0}
    fila = conn.execute("SELECT monto, anulado, cc_pago_id FROM caja_movimientos WHERE id = ?", (mov,)).fetchone()
    assert (fila[0], fila[1], fila[2]) == (100, 1, pago)


def test_un_pago_viejo_se_da_de_baja_despues_del_backfill(admin_client):
    """El caso que motiva todo: un pago hecho con el código anterior. Sin el backfill la baja se rechaza (409) y
    no toca nada; con él, el motor anula el movimiento y el arqueo deja de contar la plata."""
    cliente_id, pago_id, turno_id = _deudor_con_pago(admin_client)
    conn = admin_client.app.state.conn
    conn.execute("UPDATE caja_movimientos SET cc_pago_id = NULL WHERE cc_pago_id = ?", (pago_id,))
    conn.commit()

    rechazada = admin_client.delete(f"/api/cuenta-corriente/pagos/{pago_id}")
    assert rechazada.status_code == 409, rechazada.text
    assert admin_client.get(f"/api/cuenta-corriente/{cliente_id}").json()["saldo"] == 2000.0

    assert backfill_cc_pago_id(conn)["ligados"] == 1
    conn.commit()

    baja = admin_client.delete(f"/api/cuenta-corriente/pagos/{pago_id}")
    assert baja.status_code == 200, baja.text
    assert admin_client.get(f"/api/cuenta-corriente/{cliente_id}").json()["saldo"] == 3000.0
    anulado = conn.execute(
        "SELECT anulado FROM caja_movimientos WHERE referencia = ?", (f"cc-pago-{pago_id}",)
    ).fetchone()[0]
    assert anulado == 1
