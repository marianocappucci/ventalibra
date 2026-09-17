"""Helpers compartidos para los tests que registran ventas por la capa ERP (F3, ADR-025).

Desde F3, `/sales` es de sólo lectura (las escrituras contestan 410) y la venta se registra
completa en una sola llamada (`POST /api/ventas`, D1). Muchos tests usan una venta como paso
previo para probar OTRA cosa (tickets, recibos, balanza, módulos, logs...): este módulo es el
único lugar donde se arma esa venta, para que todos la armen igual.

Salieron de `tests/test_devoluciones.py`, el primer archivo portado. Se importan como
`from ventas_helpers import ...` (mismo mecanismo que ya usaba
`test_la_factura_declara_su_ambiente.py` para importar de `test_billing.py`).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

#: America/Argentina/Buenos_Aires, UTC-3 fijo -- mismo criterio que
#: `libracore.db.core._ar_now()`. No usar `date.today()` pelado: depende del
#: TZ del proceso que corre el test, aunque conftest lo fije hoy.
_AR = timezone(timedelta(hours=-3))


def hoy() -> str:
    """La fecha de HOY en Argentina, ISO (`YYYY-MM-DD`).

    🔴 F3 (2026-09-15): hasta acá los tests portados mandaban una `fecha` fija
    (`"2026-09-14"`) en el payload de `POST /api/ventas`. En producción el POS
    manda la fecha de HOY -- una venta fechada ayer con el turno y la caja de
    HOY es un escenario que no existe -- y todo lo que compara contra "hoy"
    (reportes, caja, turno) se rompe apenas pasa la medianoche real. Default
    de `registrar_venta()` y de los payloads de venta de toda la suite.
    """
    return datetime.now(_AR).date().isoformat()


def caja_default(client) -> int:
    """La caja que usa un test que no eligió ninguna: la predeterminada (o la
    única -- casi toda la suite corre con una sola sucursal, ver
    `app/db.py::connect`, que siembra un Location único, y `app/services/
    cajas.py::asegurar_cajas_de_todas`, que le crea su primera caja al
    arrancar `create_app()`).

    `caja_id` es obligatorio en `POST /shifts/open` desde la feature de cajas
    por sucursal (2026-09-16, ver `app/routers/shifts.py`): antes el turno
    era compartido y este helper no hacía falta.
    """
    # De la sucursal DEFAULT, no la primera predeterminada de la lista: hay una
    # predeterminada por sucursal, y desde el 2026-09-17 el backend rechaza una
    # venta sin `deposito_id` (que sale del depósito default) abierta en la
    # caja de otra sucursal (`app/ganchos.py::validar_deposito`).
    principal = client.app.state.conn.execute(
        "SELECT id FROM locations WHERE is_default = 1 LIMIT 1"
    ).fetchone()[0]
    cajas = client.get(f"/api/cajas?sucursal_id={principal}").json()
    assert cajas, "no hay ninguna caja dada de alta -- ¿se corrió asegurar_cajas_de_todas?"
    default = next((c for c in cajas if c["es_default"]), cajas[0])
    return default["id"]


def abrir_turno(client, monto_inicial=0, caja_id=None) -> int:
    """Sin turno abierto no se vende (`exigir_turno=True`): la mayoría de los tests lo necesita.

    `caja_id=None` (el default) abre sobre `caja_default(client)`."""
    if caja_id is None:
        caja_id = caja_default(client)
    abierto = client.post(
        "/shifts/open", json={"monto_inicial": monto_inicial, "caja_id": caja_id}
    )
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["turno"]["id"]


def crear_item(client, name="Yerba 1kg", price="1500.00") -> int:
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def deposito_default(client) -> int:
    """El depósito del que descuenta la venta cuando no se declara ninguno.

    Hasta F4, `POST /api/ventas` no recibía depósito en absoluto:
    `erp.stock.descontar_stock_venta` descontaba siempre del default
    (`app/db.py::connect` siembra "Depósito principal" si no hay ninguno).
    Desde F4 (2026-09-15, ADR-025) `deposito_id` es un campo ADITIVO del
    payload -- sin él (el default, `None`) el comportamiento es EXACTAMENTE
    el mismo de siempre. Sigue siendo el valor correcto para pasar como
    `deposito_id` explícito en los tests que quieren ejercitar ese campo:
    "Depósito principal" ES `is_default=1`, así que declararlo a propósito no
    cambia dónde descuenta la venta -- crear otro depósito en el test sí lo
    haría, y dejaría el stock del test y el que descuenta el motor en
    lugares distintos.
    """
    conn = client.app.state.conn
    return conn.execute("SELECT id FROM locations WHERE is_default = 1 LIMIT 1").fetchone()[0]


def con_stock(client, item_id, location_id, cantidad="20") -> None:
    client.post("/stock/adjustments", json={
        "item_id": item_id, "location_id": location_id, "quantity_delta": cantidad,
    })


def stock(client, item_id, location_id) -> Decimal:
    return Decimal(client.get(f"/stock/{item_id}", params={"location_id": location_id}).json()["quantity"])


def registrar_venta(client, item_id=None, *, precio="1500.00", cantidad="2", items=None,
                    pagos=None, cliente_id=None, fecha=None, deposito_id=None,
                    esperar=200) -> dict:
    """Registra una venta completa (D1) y devuelve el JSON de la respuesta.

    - `items`: la lista completa en el formato de `POST /api/ventas`
      (`{"nombre", "qty", "precio", "producto_id"}`); si no se pasa, se arma una línea con
      `item_id`, `precio` y `cantidad`.
    - `pagos`: por defecto, un solo pago en efectivo por el total.
    - `fecha`: por defecto, `hoy()` -- la fecha real de Argentina. Pasar una fecha fija sólo
      cuando el test necesita a propósito una venta de otro día.
    - `deposito_id`: el depósito del que descuenta ESTA venta (F4, VentaLibra multisucursal,
      ADR-025). Por defecto no se manda -- el motor descuenta del default, igual que siempre.
    - `esperar`: el status HTTP esperado (p. ej. 409 sin turno abierto); si no es 200, devuelve
      el JSON del error.
    """
    if items is None:
        items = [{"nombre": "línea", "qty": float(cantidad), "precio": float(precio),
                  "producto_id": item_id}]
    total = sum(float(i["qty"]) * float(i["precio"]) for i in items)
    payload = {
        "fecha": fecha if fecha is not None else hoy(),
        "items": items,
        "pagos": pagos or [{"medio": "efectivo", "monto": total}],
    }
    if cliente_id is not None:
        payload["cliente_id"] = cliente_id
    if deposito_id is not None:
        payload["deposito_id"] = deposito_id
    respuesta = client.post("/api/ventas", json=payload)
    assert respuesta.status_code == esperar, respuesta.text
    return respuesta.json()


def primer_sale_item_id(client, sale_id) -> int:
    """El id de `sale_items` que pide `POST /api/ventas/{vid}/devolver`.

    Mientras `GET /api/ventas/{vid}` no lo exponga (libracommerce lo agrega en `v0.16.1`), se
    lee de la base.
    """
    conn = client.app.state.conn
    return conn.execute(
        "SELECT id FROM sale_items WHERE sale_id = ? ORDER BY id LIMIT 1", (sale_id,),
    ).fetchone()[0]
