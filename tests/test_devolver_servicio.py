"""Devolver un servicio del catálogo (ADR-083; libracommerce v0.59.0, ADR-054 y migración `0007_devoluciones_de_servicio`).

Un servicio no tiene inventario: vender uno no escribe stock y, desde v0.59.0, devolverlo tampoco: se reintegra el importe y lo devuelto
queda en `sale_service_returns` (revisión 0007). La regla y sus bordes (el tope, el prorrateo, la clave, la venta mixta, el margen) los
prueba el motor (`tests/test_devolver_servicio.py`). Acá, lo que es de este producto:

- que la 0007 está aplicada en la instancia de pruebas (la cadena de `libracommerce-migrar upgrade` que corre `conftest._migrar_libracommerce`);
- que la ruta `POST /api/ventas/{id}/devolver` de VentaLibra reintegra sin tocar el stock del servicio;
- que SIN la revisión el motor contesta 503 con el comando que falta, **antes de escribir nada**, y que devolver un producto de la misma
  base sigue andando (es lo que le pasaría a una instancia a la que se le subió el pin y todavía no se le corrió la migración).
"""
from decimal import Decimal

from ventas_helpers import abrir_turno, con_stock, crear_item, deposito_default, primer_sale_item_id, registrar_venta


def _servicio(client, nombre="Corte de pelo", precio="500.00") -> int:
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post("/api/productos", json={"nombre": nombre, "unidad": "u", "precio_venta": precio, "tipo": "servicio"})
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _movimientos_de_stock(client, item_id) -> int:
    return client.app.state.conn.execute("SELECT COUNT(*) FROM stock_movements WHERE item_id = ?", (item_id,)).fetchone()[0]


def _devolver(client, sale_id, sale_item_id, cantidad, deposito):
    return client.post(f"/api/ventas/{sale_id}/devolver", json={
        "lineas": [{"sale_item_id": sale_item_id, "cantidad": cantidad}], "deposito_id": deposito})


def test_la_instancia_de_pruebas_tiene_la_revision_0007_del_motor(admin_client):
    conn = admin_client.app.state.conn
    # La cabeza es hoy la 0008 (v0.71.0, `stock_movements.origen`, ADR-093): que la 0007 esté aplicada se prueba con su tabla, abajo.
    assert [tuple(v) for v in conn.execute("SELECT version_num FROM alembic_version_libracommerce").fetchall()] == [
        ("0009_sucursal_del_nodo",)]
    columnas = {c[0] for c in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'sale_service_returns'").fetchall()}
    assert {"sale_id", "item_id", "quantity", "note"} <= columnas


def test_devolver_un_servicio_reintegra_el_importe_y_no_escribe_stock(admin_client):
    servicio = _servicio(admin_client)
    deposito = deposito_default(admin_client)
    turno = abrir_turno(admin_client)
    venta = registrar_venta(admin_client, servicio, precio="500.00", cantidad="2")
    sale_item = primer_sale_item_id(admin_client, venta["id"])
    movimientos_antes = _movimientos_de_stock(admin_client, servicio)

    parcial = _devolver(admin_client, venta["id"], sale_item, 1, deposito)
    assert parcial.status_code == 200, parcial.text
    assert parcial.json()["estado"] == "devuelta_parcial"
    resumen = admin_client.get(f"/api/turnos/{turno}").json()["resumen"]
    assert Decimal(str(resumen["total_ventas"])) == 500  # 1000 cobrados menos 500 reintegrados

    total = _devolver(admin_client, venta["id"], sale_item, 1, deposito)
    assert total.status_code == 200, total.text
    assert total.json()["estado"] == "devuelta"
    # El servicio nunca tuvo inventario: ni la venta ni las dos devoluciones escribieron en `stock_movements`.
    assert _movimientos_de_stock(admin_client, servicio) == movimientos_antes == 0
    assert admin_client.app.state.conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM sale_service_returns WHERE item_id = ?", (servicio,)).fetchone()[0] == 2
    # Y no se puede devolver más de lo vendido.
    de_mas = _devolver(admin_client, venta["id"], sale_item, 1, deposito)
    assert de_mas.status_code in (409, 422), de_mas.text


def test_sin_la_revision_0007_devolver_un_servicio_es_503_con_el_comando_y_no_escribe(admin_client):
    servicio = _servicio(admin_client)
    producto = crear_item(admin_client, "Yerba 1kg")
    deposito = deposito_default(admin_client)
    con_stock(admin_client, producto, deposito, "10")
    abrir_turno(admin_client)
    venta_servicio = registrar_venta(admin_client, servicio, precio="500.00", cantidad="1")
    venta_producto = registrar_venta(admin_client, producto, precio="1500.00", cantidad="2")
    conn = admin_client.app.state.conn
    # El motor sondea la tabla por metadatos: una base a la que se le subió el pin y todavía no se le corrió la migración no la tiene.
    conn.execute("DROP TABLE sale_service_returns")
    conn.commit()
    pagos_antes = conn.execute("SELECT COUNT(*) FROM caja_movimientos").fetchone()[0]

    r = _devolver(admin_client, venta_servicio["id"], primer_sale_item_id(admin_client, venta_servicio["id"]), 1, deposito)

    assert r.status_code == 503, r.text
    assert "libracommerce-migrar upgrade" in r.json()["detail"] and "0007_devoluciones_de_servicio" in r.json()["detail"]
    assert conn.execute("SELECT COUNT(*) FROM caja_movimientos").fetchone()[0] == pagos_antes  # no reintegró nada
    # Devolver un producto de la misma base sigue andando: sólo falla lo que pide devolver un servicio.
    ok = _devolver(admin_client, venta_producto["id"], primer_sale_item_id(admin_client, venta_producto["id"]), 1, deposito)
    assert ok.status_code == 200, ok.text
