"""La nota de crédito en VentaLibra: la ruta del motor, y que anular una venta facturada pase por ella.

Qué se prueba acá es **el montaje**: la ruta existe, es solo admin, no trae las otras del router de comprobantes, y el
flujo completo que la necesita. La lógica de la nota (guardas, armado, abono a la cuenta corriente) es del motor
(`libracore.notas_de_credito`, ADR-014/016/017) y la prueba el motor; la exigencia de la nota para anular es de
libracommerce (ADR-032).
"""

from test_billing import _abrir_turno, _make_item, _registrar_venta


def _venta_facturada(client):
    item_id = _make_item(client, price="1000.00")
    _abrir_turno(client)
    vid = _registrar_venta(client, item_id, precio="1000.00").json()["id"]
    facturada = client.post(f"/api/ventas/{vid}/facturar")
    assert facturada.status_code == 200, facturada.text
    return vid, facturada.json()["factura"]


def test_la_unica_ruta_de_facturas_es_la_nota_de_credito(admin_client):
    """Los otros once endpoints del router de comprobantes (alta manual, cobro, borrado) no se montan."""
    # Por el esquema OpenAPI de la app y no por `app.routes`: el TestClient puede traer la app envuelta.
    esquema = admin_client.app.openapi()
    rutas = {(metodo.upper(), ruta) for ruta, ops in esquema["paths"].items()
             if ruta.startswith("/api/facturas") for metodo in ops}
    assert rutas == {("POST", "/api/facturas/{factura_id}/nota-credito")}


def test_solo_un_admin_emite_la_nota(admin_client, staff_client):
    _vid, factura = _venta_facturada(admin_client)
    assert staff_client.post(f"/api/facturas/{factura['id']}/nota-credito").status_code == 403
    # El admin pasa el gate: la nota se emite (el CAE de dev es el mock del motor).
    assert admin_client.post(f"/api/facturas/{factura['id']}/nota-credito").status_code == 200


def test_anular_una_venta_facturada_pide_la_nota_antes(admin_client):
    vid, factura = _venta_facturada(admin_client)

    r = admin_client.post(f"/api/ventas/{vid}/anular")
    assert r.status_code == 409, r.text
    assert "nota de crédito" in r.json()["detail"]
    assert admin_client.get(f"/api/ventas/{vid}").json()["status"] != "cancelled"

    nota = admin_client.post(f"/api/facturas/{factura['id']}/nota-credito")
    assert nota.status_code == 200, nota.text
    assert nota.json()["cbte_asoc_nro"] == factura["numero"]

    assert admin_client.post(f"/api/ventas/{vid}/anular").status_code == 200
    assert admin_client.get(f"/api/ventas/{vid}").json()["status"] == "cancelled"


def test_una_venta_sin_factura_se_anula_como_siempre(admin_client):
    item_id = _make_item(admin_client, price="1000.00")
    _abrir_turno(admin_client)
    vid = _registrar_venta(admin_client, item_id, precio="1000.00").json()["id"]
    assert admin_client.post(f"/api/ventas/{vid}/anular").status_code == 200


def test_el_cajero_puede_anular_lo_no_facturado_pero_no_emitir_la_nota(admin_client, staff_client):
    """Decisión del 2026-09-15 (el staff anula) sigue en pie; lo facturado por ARCA pide a un admin."""
    vid, _factura = _venta_facturada(admin_client)
    r = staff_client.post(f"/api/ventas/{vid}/anular")
    assert r.status_code == 409, "con factura CAE hace falta la nota, y la emite un admin"
