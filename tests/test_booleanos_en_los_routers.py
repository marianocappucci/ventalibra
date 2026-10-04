"""Ningún campo numérico de la API acepta un booleano (ADR-028 del motor, ADR-063 y ADR-065 de VentaLibra).

Pydantic, en modo laxo —el de FastAPI—, convierte `true` en `1` y `false` en `0` en cualquier campo `int`/`float` antes de que el servicio lo mire: `{"monto": true}` entraba
como un pago de 1 peso. `libracommerce.testing.campos_numericos_que_aceptan_booleano(app)` (la misma guardia vive también en `libracore.testing`) recorre las rutas REALES de la app completa
e instancia cada modelo con `True`/`False` en cada hoja numérica; una lista vacía es lo esperado.

Cubiertos y exigidos por este test: los routers de VentaLibra (`app/routers/*`), los del motor (`libracommerce.web`), los de `libracore` (cajas, turnos, cierre diario, cuenta corriente, egresos,
tesorería, ARCA, facturas, comprobantes, remitos, presupuestos, MercadoPago; libracore v1.125.0) y los de `libraauth` (SMTP y códigos demo; v0.46.1). Hasta el 2026-10-04 las librerías compartidas tenían
24 campos sin arreglar que este test fijaba en una lista; ya no queda ninguno.

La guardia sólo ve los campos TIPADOS: un `dict`, un `list[dict]` o un `request.json()` con un número adentro no lo detecta y se revisa a mano (el barrido de `libracore` encontró uno, `pagos[].monto`, ya arreglado).
"""
from libracommerce.testing import campos_numericos_que_aceptan_booleano


def test_ningun_campo_numerico_de_la_api_acepta_un_booleano(admin_client):
    encontrados = sorted(campos_numericos_que_aceptan_booleano(admin_client.app))
    assert not encontrados, f"campos numéricos que aceptan un booleano (aplicar `sin_booleanos`): {encontrados}"


def test_los_routers_rechazan_el_booleano_con_422(admin_client):
    """De punta a punta por HTTP, con la app completa: los campos propios de VentaLibra, y los de las librerías que antes eran el dinero (pagos, egresos, tesorería, turnos, SMTP)."""
    casos = [
        # VentaLibra
        ("post", "/catalog/categories", {"name": "X", "parent_id": True}),
        ("post", "/catalog/units", {"code": "ZZ", "name": "Zeta", "decimal_scale": True}),
        ("put", "/settings/scale", {"code_digits": True}),
        ("put", "/settings/scale", {"divisor": True}),
        ("put", "/settings/ticket", {"fuente_size": True}),
        # libracore: dinero
        ("post", "/api/cuenta-corriente/1/pagar", {"monto": True}),
        ("post", "/api/egresos/1/pagar", {"monto": True}),
        ("post", "/api/tesoreria/transferencia", {"cuenta_origen_id": 1, "cuenta_destino_id": 2, "monto": True}),
        ("post", "/api/turnos/abrir", {"caja_id": 1, "monto_inicial": True}),
        ("post", "/api/turnos/1/cerrar", {"monto_declarado": True}),
        ("put", "/config/arca", {"punto_venta": True}),
        # libraauth
        ("put", "/admin/smtp", {"host": "h", "port": True}),
    ]
    for metodo, ruta, cuerpo in casos:
        r = getattr(admin_client, metodo)(ruta, json=cuerpo)
        assert r.status_code == 422, (ruta, cuerpo, r.status_code, r.text)
        assert "no un booleano" in r.text, (ruta, cuerpo, r.text)
