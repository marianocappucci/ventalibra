"""Ningún campo numérico de la API acepta un booleano (ADR-028 del motor, ADR-063 de VentaLibra).

Pydantic, en modo laxo —el de FastAPI—, convierte `true` en `1` y `false` en `0` en cualquier campo `int`/`float` antes de que el servicio lo mire: `{"monto": true}` entraba
como un pago de 1 peso. `libracommerce.testing.campos_numericos_que_aceptan_booleano(app)` recorre las rutas REALES de la app completa e instancia cada modelo con `True`/`False`
en cada hoja numérica; una lista vacía es lo esperado.

Los routers de VentaLibra (`app/routers/*`) y los del motor (`libracommerce.web`) están cubiertos y este test lo exige. Quedan **conocidos y sin arreglar** los de las librerías compartidas
`libracore` (cajas, turnos, cierre diario, cuenta corriente, egresos, tesorería, ARCA) y `libraauth` (SMTP): no se arreglan en este repo sino en cada librería, con su release y el pin de los
productos. Se listan abajo para que el test los fije: si una librería los arregla, la igualdad falla y obliga a sacar la entrada (y si aparece uno nuevo en cualquier router, falla).
"""
from libracommerce.testing import campos_numericos_que_aceptan_booleano

#: (ruta, campo) de las librerías compartidas que todavía aceptan un booleano. Cada uno se arregla en `libracore`/`libraauth` (no acá).
PENDIENTES_DE_LAS_LIBRERIAS = {
    # libracore.caja_router
    ("POST /api/cajas", "punto_venta"), ("POST /api/cajas", "sucursal_id"), ("PUT /api/cajas/{cid}", "punto_venta"), ("PUT /api/cajas/{cid}", "sucursal_id"),
    ("POST /api/cierre-diario/cerrar", "sucursal_id"), ("POST /api/turnos/abrir", "caja_id"), ("POST /api/turnos/abrir", "monto_inicial"),
    ("POST /api/turnos/{tid}/cerrar", "monto_declarado"),
    # libracore.cuenta_corriente_router
    ("POST /api/cuenta-corriente/{cliente_id}/pagar", "caja_id"), ("POST /api/cuenta-corriente/{cliente_id}/pagar", "facturas[]"),
    ("POST /api/cuenta-corriente/{cliente_id}/pagar", "monto"),
    # libracore.egresos_router
    ("POST /api/egresos", "iva_pct"), ("POST /api/egresos", "monto_neto"), ("POST /api/egresos", "proveedor_id"),
    ("POST /api/egresos/{eid}/pagar", "caja_id"), ("POST /api/egresos/{eid}/pagar", "monto"),
    # libracore.tesoreria_router
    ("POST /api/tesoreria/cuentas", "saldo_inicial"), ("PUT /api/tesoreria/cuentas/{cid}", "saldo_inicial"),
    ("POST /api/tesoreria/cuentas/{cid}/movimiento", "monto"), ("POST /api/tesoreria/transferencia", "cuenta_destino_id"),
    ("POST /api/tesoreria/transferencia", "cuenta_origen_id"), ("POST /api/tesoreria/transferencia", "monto"),
    # libracore.arca_router y libraauth.session_auth
    ("PUT /config/arca", "punto_venta"), ("PUT /admin/smtp", "port"),
}


def test_ningun_campo_numerico_de_los_routers_propios_acepta_un_booleano(admin_client):
    encontrados = {(ruta, campo) for ruta, campo, _tipo in campos_numericos_que_aceptan_booleano(admin_client.app)}
    nuevos = sorted(encontrados - PENDIENTES_DE_LAS_LIBRERIAS)
    assert not nuevos, f"campos numéricos que aceptan un booleano y no son de las librerías compartidas: {nuevos}"


def test_los_pendientes_de_las_librerias_siguen_siendo_reales(admin_client):
    """Si `libracore`/`libraauth` arreglan uno, hay que sacarlo de la lista de arriba: la lista no es un cajón donde esconder lo que ya no pasa."""
    encontrados = {(ruta, campo) for ruta, campo, _tipo in campos_numericos_que_aceptan_booleano(admin_client.app)}
    arreglados = sorted(PENDIENTES_DE_LAS_LIBRERIAS - encontrados)
    assert not arreglados, f"ya no aceptan un booleano (sacarlos de PENDIENTES_DE_LAS_LIBRERIAS): {arreglados}"


def test_los_routers_propios_rechazan_el_booleano_con_422(admin_client):
    """Lo mismo, de punta a punta por HTTP en los siete campos de VentaLibra que se arreglaron."""
    casos = [
        ("post", "/catalog/categories", {"name": "X", "parent_id": True}),
        ("post", "/catalog/units", {"code": "ZZ", "name": "Zeta", "decimal_scale": True}),
        ("put", "/settings/scale", {"code_digits": True}),
        ("put", "/settings/scale", {"value_digits": True}),
        ("put", "/settings/scale", {"divisor": True}),
        ("put", "/settings/scale", {"total_digits": True}),
        ("put", "/settings/ticket", {"fuente_size": True}),
    ]
    for metodo, ruta, cuerpo in casos:
        r = getattr(admin_client, metodo)(ruta, json=cuerpo)
        assert r.status_code == 422, (ruta, cuerpo, r.status_code, r.text)
        assert "no un booleano" in r.text, (ruta, cuerpo, r.text)
