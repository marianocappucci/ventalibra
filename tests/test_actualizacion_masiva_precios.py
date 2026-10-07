"""Actualización masiva de precios desde la planilla de un proveedor
(roadmap de producto, no una adopción de motores: no existía en ningún
producto de la familia hasta esto). El cálculo del margen y el parseo de la
planilla ya los prueba la suite del motor (`libracommerce`); acá se prueba el
montaje: que esté de admin y que un producto real de este producto se
actualice de punta a punta.
"""

from io import BytesIO

from openpyxl import Workbook

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _planilla(filas: list[tuple], encabezados=("Código", "Costo")) -> bytes:
    wb = Workbook()
    hoja = wb.active
    hoja.append(list(encabezados))
    for fila in filas:
        hoja.append(list(fila))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _archivo(contenido: bytes):
    return {"archivo": ("precios.xlsx", contenido, _XLSX)}


def _buscar(client, pid):
    """`build_productos_router` no tiene `GET /{pid}`: sólo listado, códigos y variantes."""
    return next(p for p in client.get("/api/productos").json() if p["id"] == pid)


def _crear_producto(client, codigo="7791234567890", venta="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post(
        "/api/productos",
        json={"nombre": "Yerba", "unidad": "u", "codigo": codigo, "precio_venta": venta, "precio_costo": "1000.00"},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def test_un_cajero_no_puede_usarla(cajero_client):
    assert cajero_client.post(
        "/api/actualizacion-masiva/precios/preview", files=_archivo(_planilla([("111", 100)]))
    ).status_code == 403


def test_preview_no_escribe_nada(admin_client):
    pid = _crear_producto(admin_client)
    r = admin_client.post("/api/actualizacion-masiva/precios/preview", files=_archivo(_planilla([("7791234567890", 1200)])))
    assert r.status_code == 200, r.text
    assert r.json()["actualizaciones"][0]["venta_nueva"] == 1800.0

    producto = _buscar(admin_client, pid)
    assert producto["precio_costo"] == 1000.0  # sin cambios


def test_aplicar_actualiza_el_producto_manteniendo_el_margen(admin_client):
    pid = _crear_producto(admin_client)
    r = admin_client.post("/api/actualizacion-masiva/precios/aplicar", files=_archivo(_planilla([("7791234567890", 1200)])))
    assert r.status_code == 200, r.text

    producto = _buscar(admin_client, pid)
    assert producto["precio_costo"] == 1200.0
    assert producto["precio_venta"] == 1800.0  # margen 1.5x conservado


def test_un_codigo_sin_producto_se_reporta_sin_romper_el_resto(admin_client):
    _crear_producto(admin_client, codigo="111")
    r = admin_client.post("/api/actualizacion-masiva/precios/preview", files=_archivo(_planilla([
        ("111", 1200), ("000", 500),
    ])))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["actualizaciones"]) == 1
    assert body["no_encontrados"] == [{"codigo": "000", "motivo": "Ningún producto activo tiene este código."}]
