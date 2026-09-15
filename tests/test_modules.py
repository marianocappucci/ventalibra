"""Gating por módulo del plan (ADR-009): catálogo, stock y venta/POS nunca se
gatean; sólo `facturacion` está condicionado.

Portado a F3 (2026-09-14, DECISIONS.md ADR-025): registrar una venta ya no es
`POST /sales` (borrador) + `.../items` + `.../confirm` -- es una sola llamada,
`POST /api/ventas` (D1, helper `registrar_venta` de `ventas_helpers.py`).
Facturar dejó de ser el flag `invoice` de esa llamada: es un paso aparte,
`POST /api/ventas/{vid}/facturar` (D2/D6, `libracore.ventas_cobro_router`).

🔴 **El invariante de ADR-009 no venía solo por portar los tests.** Medido
armando la app con `facturacion` en `False` y facturando una venta real:
`POST /api/ventas/{vid}/facturar` contestaba **200** igual -- el mount de
`app/main.py` para esa ruta no traía ningún `require_module`, a diferencia
del `confirm_sale` legado, que sí lo chequeaba antes de tocar nada. Se agregó
el gate en `app/main.py` (ver el comentario ahí, sobre por qué va sólo en
`/facturar` y no en todo el router de cobro que comparte con `/mp-qr` y
`/mp-status`) -- no es un cambio de test, es la causa real de que estos
cuatro test fallaran.
"""
from ventas_helpers import abrir_turno, crear_item, deposito_default, registrar_venta


def _disable(client, modulo: str) -> None:
    client.app.state.modules.set_enabled(modulo, False)


def test_all_modules_enabled_by_default(admin_client):
    assert admin_client.app.state.modules.get_all() == {"facturacion": True}


def test_billing_router_requires_facturacion_module(admin_client):
    _disable(admin_client, "facturacion")
    assert admin_client.get("/config/arca").status_code == 403


def test_registrar_venta_sin_facturar_ignora_el_modulo_apagado(admin_client):
    _disable(admin_client, "facturacion")
    item_id = crear_item(admin_client)
    deposito_default(admin_client)
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id)
    assert venta["factura_id"] is None


def test_facturar_exige_el_modulo_facturacion(admin_client):
    _disable(admin_client, "facturacion")
    item_id = crear_item(admin_client)
    deposito_default(admin_client)
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id)
    respuesta = admin_client.post(f"/api/ventas/{venta['id']}/facturar")
    assert respuesta.status_code == 403


def test_facturar_funciona_con_el_modulo_habilitado(admin_client):
    item_id = crear_item(admin_client)
    deposito_default(admin_client)
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id)
    respuesta = admin_client.post(f"/api/ventas/{venta['id']}/facturar")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["factura"] is not None


def test_catalog_stock_and_sales_are_never_gated(admin_client):
    _disable(admin_client, "facturacion")
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    assert admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "5"},
    ).status_code == 200
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id)
    assert venta["id"] is not None
