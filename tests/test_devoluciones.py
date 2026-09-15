"""Anulación y devolución, sobre la capa ERP de LibraCommerce (F3, ADR-025).

Lo que ordena estos tests: **deshacer una venta tiene que dejar todo como
antes** — el stock de vuelta en el depósito y la plata fuera de la caja — y
no puede ejecutarse dos veces. Un reintento que reponga stock por segunda
vez inventa mercadería que no existe.

Portado desde el modelo de borrador+confirmar (`POST /sales`, retirado): D1
registra la venta completa en una sola llamada (`POST /api/ventas`), y
`POST /api/ventas/{vid}/anular` / `.../devolver` reemplazan a
`/sales/{id}/cancel` / `.../returns`.

🔴 **Dos diferencias de forma, no sólo de ruta, documentadas en el plan
("Límites conocidos de F1, para F3"):**

1. `devolver_items` indexa por **`sale_items.id`**, no por la posición de la
   línea (`index`) que usaba el modelo viejo. La API de la venta (`GET
   /api/ventas/{vid}`) no expone ese id -- se lee directo de la base, que es
   exactamente el gap que el plan deja para F4 (la pantalla todavía no existe).
2. El estado de una devolución parcial/total vuelve en la clave **`estado`**
   (`"devuelta_parcial"`/`"devuelta"`), no en `status` (que se queda en
   `"confirmed"` -- ver `libracommerce.erp.ventas.estado_de_row`). El modelo
   viejo tenía un único campo `status` con esos valores.
"""
from decimal import Decimal

from ventas_helpers import (
    abrir_turno,
    con_stock,
    crear_item,
    deposito_default,
    hoy,
    primer_sale_item_id,
    registrar_venta,
    stock,
)


def _venta(client, item_id, precio="1500.00", cantidad="2", pagos=None, customer_id=None):
    """Compat: `registrar_venta()` de `ventas_helpers.py` devuelve el JSON
    completo (lo necesitan otros archivos); este módulo sólo usaba el id."""
    return registrar_venta(
        client, item_id, precio=precio, cantidad=cantidad, pagos=pagos, cliente_id=customer_id,
    )["id"]


# ── Anulación ────────────────────────────────────────────────────────────────

def test_anular_repone_el_stock_y_saca_la_plata_de_la_caja(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "20")
    turno_id = abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="3")

    assert stock(admin_client, item_id, location_id) == 17
    assert Decimal(str(
        admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]["total_ventas"]
    )) == 4500

    anulada = admin_client.post(f"/api/ventas/{sale_id}/anular")
    assert anulada.status_code == 200, anulada.text
    assert anulada.json()["status"] == "cancelled"

    # Todo como antes: la mercadería volvió y la plata salió.
    assert stock(admin_client, item_id, location_id) == 20
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 0


def test_anular_dos_veces_no_repone_dos_veces(admin_client):
    """El reintento del botón no puede inventar mercadería."""
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="2")

    admin_client.post(f"/api/ventas/{sale_id}/anular")
    admin_client.post(f"/api/ventas/{sale_id}/anular")

    assert stock(admin_client, item_id, location_id) == 10


def test_anular_una_venta_fiada_le_baja_la_deuda_al_cliente(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    cliente = admin_client.post("/customers", json={"display_name": "Vecina"}).json()["id"]
    sale_id = _venta(admin_client, item_id, cantidad="2",
                     pagos=[{"medio": "cuenta_corriente", "monto": 3000}],
                     customer_id=cliente)
    assert Decimal(str(admin_client.get(f"/accounts/{cliente}").json()["saldo"])) == 3000

    anulada = admin_client.post(f"/api/ventas/{sale_id}/anular")
    assert anulada.status_code == 200, anulada.text

    assert Decimal(str(admin_client.get(f"/accounts/{cliente}").json()["saldo"])) == 0


def test_anular_una_venta_inexistente_es_404(admin_client):
    assert admin_client.post("/api/ventas/9999/anular").status_code == 404


def test_anular_una_venta_pendiente_de_qr_no_toca_la_caja_y_vence_el_pago(admin_client):
    """🔴 Reemplaza a `test_no_se_anula_un_borrador` (retirado: D1 no tiene
    más borradores por posición). El caso equivalente en el modelo nuevo es
    una venta PENDIENTE de QR (`cobrar_con_qr`, nadie escaneó todavía):
    `libracommerce.erp.ventas.anular_venta` sólo revierte los pagos
    ACREDITADOS -- nunca entró plata de un `pendiente`, así que revertirlo
    sacaría de la caja algo que no estaba. El stock sí se repone (se
    descontó al registrar, no al cobrar) y el pago pendiente pasa a
    `vencido` -- ni `aprobado` (no entró) ni `rechazado` (nadie lo rechazó,
    se cerró antes), y así `acreditar_pago_qr` no lo vuelve a tocar si el
    cliente escanea después de todos modos."""
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    turno_id = abrir_turno(admin_client)

    creada = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 2, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "mercadopago", "monto": 3000.0, "cobrar_con_qr": True}],
    })
    assert creada.status_code == 200, creada.text
    sale_id = creada.json()["id"]
    assert creada.json()["estado"] == "pendiente"
    assert stock(admin_client, item_id, location_id) == 8

    anulada = admin_client.post(f"/api/ventas/{sale_id}/anular")
    assert anulada.status_code == 200, anulada.text

    # El stock vuelve: se descontó al registrar, la anulación lo repone
    # igual que a cualquier otra venta.
    assert stock(admin_client, item_id, location_id) == 10
    # La caja NO se movió: la plata del QR nunca entró.
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 0

    conn = admin_client.app.state.conn
    estado_pago = conn.execute(
        "SELECT estado FROM ventas_pagos WHERE venta_id = ?", (sale_id,),
    ).fetchone()[0]
    assert estado_pago == "vencido"


# ── Devolución parcial ───────────────────────────────────────────────────────

def test_devolver_una_parte_repone_solo_esa_parte(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "20")
    turno_id = abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="5")
    assert stock(admin_client, item_id, location_id) == 15
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    devuelta = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 2}], "deposito_id": location_id,
    })
    assert devuelta.status_code == 200, devuelta.text
    assert devuelta.json()["estado"] == "devuelta_parcial"

    assert stock(admin_client, item_id, location_id) == 17
    # Se reintegraron 2 x 1500 = 3000 de los 7500 cobrados.
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 4500


def test_devolver_todo_deja_la_venta_como_devuelta(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="2")
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    devuelta = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 2}], "deposito_id": location_id,
    })

    assert devuelta.json()["estado"] == "devuelta"
    assert stock(admin_client, item_id, location_id) == 10


def test_no_se_puede_devolver_mas_de_lo_vendido(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="2")
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    respuesta = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 5}], "deposito_id": location_id,
    })
    assert respuesta.status_code == 422
    # Y el stock no se movió por el intento.
    assert stock(admin_client, item_id, location_id) == 8


def test_las_devoluciones_parciales_se_acumulan(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="3")
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 1}], "deposito_id": location_id,
    })
    segunda = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 2}], "deposito_id": location_id,
    })

    assert segunda.json()["estado"] == "devuelta"
    assert stock(admin_client, item_id, location_id) == 10


def test_devolver_una_linea_que_no_existe_es_422(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="1")

    respuesta = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": 999999, "cantidad": 1}], "deposito_id": location_id,
    })
    assert respuesta.status_code == 422


def test_devolver_sin_indicar_lineas_es_422(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="1")

    respuesta = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [], "deposito_id": location_id,
    })
    assert respuesta.status_code == 422


def test_devolver_a_cuenta_corriente_baja_la_deuda(admin_client):
    """Si la compra estaba fiada y todavía no se pagó, devolver no saca plata
    del cajón: descuenta lo que el cliente debe."""
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    turno_id = abrir_turno(admin_client)
    cliente = admin_client.post("/customers", json={"display_name": "Vecina"}).json()["id"]
    sale_id = _venta(admin_client, item_id, cantidad="2",
                     pagos=[{"medio": "cuenta_corriente", "monto": 3000}],
                     customer_id=cliente)
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    devuelta = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 1}],
        "deposito_id": location_id, "medio_pago": "cuenta_corriente",
    })
    assert devuelta.status_code == 200, devuelta.text

    assert Decimal(str(admin_client.get(f"/accounts/{cliente}").json()["saldo"])) == 1500
    # La caja no se movió.
    resumen = admin_client.get(f"/shifts/{turno_id}/summary").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 0


def test_no_se_devuelve_a_cuenta_corriente_sin_cliente(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="1")
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    respuesta = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 1}],
        "deposito_id": location_id, "medio_pago": "cuenta_corriente",
    })
    assert respuesta.status_code == 422


def test_se_puede_devolver_por_otro_medio_del_que_se_cobro(admin_client):
    # Se cobró con tarjeta y se devuelve en efectivo: pasa en el mostrador.
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="1",
                     pagos=[{"medio": "tarjeta_debito", "monto": 1500}])
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    devuelta = admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 1}],
        "deposito_id": location_id, "medio_pago": "efectivo",
    })
    assert devuelta.status_code == 200, devuelta.text
    assert devuelta.json()["estado"] == "devuelta"


# ── Permisos ─────────────────────────────────────────────────────────────
#
# `libracommerce.web.ventas_router.build_ventas_router(solo_admin=...)` gatea
# `POST /{vid}/anular` y `.../devolver` para admin -- verificado en el código
# instalado (`.venv/.../libracommerce/web/ventas_router.py`): el `gate_anular`
# que arma con `solo_admin` no cuelga de ninguna otra ruta de ese router.
# `app/main.py` NO le pasa `solo_admin` a propósito: hasta hoy, en este
# producto, un cajero (staff) podía anular (`/sales/{id}/cancel`, retirado) y
# devolver (`/sales/{id}/returns`, retirado) -- el router llevaba `staff_or_
# admin` y el endpoint en sí sólo pedía sesión (`get_current_user`), sin
# ningún chequeo de rol propio. Restringirlo a admin sería una decisión que
# nadie tomó -- se preserva el permiso de siempre.


def test_un_staff_puede_anular_y_devolver(admin_client, staff_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)

    sale_id = _venta(admin_client, item_id, cantidad="2")
    anulada = staff_client.post(f"/api/ventas/{sale_id}/anular")
    assert anulada.status_code == 200, anulada.text

    sale_id_2 = _venta(admin_client, item_id, cantidad="2")
    sale_item_id = primer_sale_item_id(admin_client, sale_id_2)
    devuelta = staff_client.post(f"/api/ventas/{sale_id_2}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 1}], "deposito_id": location_id,
    })
    assert devuelta.status_code == 200, devuelta.text


def test_sin_sesion_no_se_puede_anular_ni_devolver(admin_client):
    """El control: el permiso amplio (staff puede) no es "sin sesión pasa
    igual" -- sigue haciendo falta estar logueado."""
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="2")
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    assert admin_client.post("/auth/logout").status_code == 200
    assert admin_client.post(f"/api/ventas/{sale_id}/anular").status_code == 401
    assert admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 1}], "deposito_id": location_id,
    }).status_code == 401


# ── GET /ventas/{id}/devuelto (F4, lo que la pantalla usa para topear) ────
#
# `GET /api/ventas/{id}` no expone cuánto se devolvió (`sale_items.quantity`
# es el snapshot de lo vendido, nunca cambia): esto lee el ledger
# `stock_movements` con el MISMO criterio que `libracommerce.erp.ventas.
# devolver_items` usa para validar -- ver `app/routers/ventas_extra.py`.


def test_devuelto_arranca_en_cero(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="2")

    respuesta = admin_client.get(f"/ventas/{sale_id}/devuelto")
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["por_clave"] == []
    # Una sola venta, un solo depósito: se puede determinar sin ambigüedad.
    assert datos["deposito_id"] == location_id


def test_devuelto_refleja_la_devolucion_parcial(admin_client):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id, "10")
    abrir_turno(admin_client)
    sale_id = _venta(admin_client, item_id, cantidad="5")
    sale_item_id = primer_sale_item_id(admin_client, sale_id)

    admin_client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": 2}], "deposito_id": location_id,
    })

    datos = admin_client.get(f"/ventas/{sale_id}/devuelto").json()
    assert len(datos["por_clave"]) == 1
    fila = datos["por_clave"][0]
    assert fila["producto_id"] == item_id
    assert fila["variante_id"] is None
    assert fila["cantidad"] == 2.0


def test_devuelto_de_una_venta_inexistente_no_revienta(admin_client):
    """Sin filas que agregar: `por_clave` vacío y depósito indeterminado, no
    un 404 -- `sale_id` es sólo la clave de búsqueda del ledger, no algo que
    esta lectura valide contra `sales`."""
    respuesta = admin_client.get("/ventas/999999/devuelto")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"por_clave": [], "deposito_id": None}
