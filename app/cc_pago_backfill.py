"""Backfill de `caja_movimientos.cc_pago_id` a partir de la referencia `cc-pago-<id>`.

`libracore` v1.117.0 (migración `0013`) liga cada movimiento de caja de un pago a cuenta con su `cc_pagos.id`, y
dar de baja el pago anula en el motor todos los que lo llevan. Los pagos que VentaLibra registró **antes** no tienen
esa columna, pero su movimiento sí lleva la referencia `cc-pago-<id>` (ver `app/cuenta_corriente_ganchos.py`): es la
única forma de encontrarlo, y por eso el gancho de baja conservaba esa búsqueda.

Esta función completa la columna desde esa referencia, y con eso el gancho puede dejar de buscar por texto.

Sólo toca lo que se puede afirmar:

- movimientos con `cc_pago_id` vacío y una referencia con **exactamente** la forma `cc-pago-<número>`;
- cuyo pago **todavía existe** en `cc_pagos`. Un pago ya borrado dejó su movimiento anulado y sin dueño: ligarlo a un
  id que no existe (o que la secuencia podría reutilizar) sería inventar un vínculo.

Es idempotente: una segunda corrida no encuentra nada que hacer. No cambia ningún monto, medio ni `anulado`.
"""
import re

_REFERENCIA = re.compile(r"^cc-pago-([0-9]+)$")


def backfill_cc_pago_id(conn) -> dict:
    """Devuelve `{"ligados": n, "huerfanos": m}`: los movimientos completados y los que tienen la referencia
    pero cuyo pago ya no existe (quedan como estaban)."""
    filas = conn.execute(
        "SELECT id, referencia FROM caja_movimientos WHERE cc_pago_id IS NULL AND referencia LIKE 'cc-pago-%'"
    ).fetchall()
    ligados = huerfanos = 0
    for fila in filas:
        coincide = _REFERENCIA.match(fila[1] or "")
        if coincide is None:
            continue
        pago_id = int(coincide.group(1))
        if conn.execute("SELECT 1 FROM cc_pagos WHERE id = ?", (pago_id,)).fetchone() is None:
            huerfanos += 1
            continue
        conn.execute("UPDATE caja_movimientos SET cc_pago_id = ? WHERE id = ?", (pago_id, fila[0]))
        ligados += 1
    return {"ligados": ligados, "huerfanos": huerfanos}
