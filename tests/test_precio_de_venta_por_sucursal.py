"""El precio de venta por sucursal en la validación (ADR-083; `VentaPayload.sucursal_id` y `OpcionesVentas.sucursal_de_la_venta` de
libracommerce v0.59.0, ADR-058 del motor).

La regla y sus casos de borde (la costura, `exigir_precio_de_sucursal`, el quiebre conviviendo con el precio de sucursal, las
promociones) los prueba `libracommerce` (`tests/test_precio_de_venta_por_sucursal.py`). Acá, lo que es de este producto:

- que **un POS que declara `sucursal_id`** cobra el precio de la sucursal (el que cotiza `POST /api/listas-precio/{id}/precios` con
  esa sucursal) y que el general es un 409 que trae la `sucursal_id` que usó el servidor;
- que **un pedido que no la manda** (un POS viejo, un cliente armado a mano) ya no elige el precio general:
  `exigir_precio_de_sucursal` está prendida en `app/main.py` (ADR-085) y se valida contra el de la sucursal de la venta;
- que la sucursal la decide el depósito de la venta (la costura por defecto del motor, que es la sucursal del turno: `validar_deposito`
  de `app/ganchos.py` rechaza un depósito de otra sucursal), no lo que diga el pedido.
"""
from ventas_helpers import abrir_turno, crear_item, hoy, sucursal_default

GENERAL = 100.0
DE_LA_SUCURSAL = 90.0


def _venta(client, precio, **extra):
    item = {"nombre": "línea", "qty": 1, "precio": precio, "producto_id": extra.pop("producto_id")}
    return client.post("/api/ventas", json={
        "fecha": hoy(), "items": [item], "pagos": [{"medio": "efectivo", "monto": precio}], **extra})


def _escenario(admin_client):
    """Un producto a 100 de lista general y 90 en la sucursal predeterminada, con la lista como predeterminada."""
    producto = crear_item(admin_client, "Alfajor", "100.00")
    lista = admin_client.post("/api/listas-precio", json={"nombre": "General"}).json()
    assert admin_client.post(f"/api/listas-precio/{lista['id']}/set-default").status_code == 200
    sucursal = sucursal_default(admin_client)
    for extra in ({}, {"sucursal_id": sucursal["id"]}):
        monto = DE_LA_SUCURSAL if extra else GENERAL
        r = admin_client.post(f"/api/listas-precio/{lista['id']}/items/{producto}/precio-vigente",
                              json={"monto": monto, "desde": "2026-01-01T00:00:00", **extra})
        assert r.status_code == 200, r.text
    return producto, lista["id"], sucursal["id"]


def test_la_cotizacion_con_la_sucursal_da_el_precio_de_la_sucursal(admin_client):
    producto, lista, sucursal = _escenario(admin_client)
    cotizar = lambda **extra: admin_client.post(  # noqa: E731
        f"/api/listas-precio/{lista}/precios", json={"lineas": [{"producto_id": producto, "cantidad": 1}], **extra})
    assert cotizar(sucursal_id=sucursal).json()["precios"][0]["precio"] == DE_LA_SUCURSAL
    assert cotizar().json()["precios"][0]["precio"] == GENERAL


def test_un_pos_que_declara_la_sucursal_cobra_el_precio_de_la_sucursal(admin_client, cajero_client):
    producto, _, sucursal = _escenario(admin_client)
    abrir_turno(cajero_client)

    ok = _venta(cajero_client, DE_LA_SUCURSAL, producto_id=producto, sucursal_id=sucursal)
    assert ok.status_code == 200, ok.text
    assert ok.json()["total"] == DE_LA_SUCURSAL


def test_el_precio_general_con_la_sucursal_declarada_es_409_y_dice_que_sucursal_uso_el_servidor(admin_client, cajero_client):
    producto, _, sucursal = _escenario(admin_client)
    abrir_turno(cajero_client)
    antes = admin_client.app.state.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]

    r = _venta(cajero_client, GENERAL, producto_id=producto, sucursal_id=sucursal)

    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    # Lo que lee `Pos.tsx` (`lib/precios-distintos.ts`): el código y los precios esperados, más la sucursal (opcional).
    assert detalle["codigo"] == "precios_distintos"
    assert detalle["sucursal_id"] == sucursal
    assert [(p["indice"], p["enviado"], p["esperado"]) for p in detalle["precios"]] == [(0, GENERAL, DE_LA_SUCURSAL)]
    assert admin_client.app.state.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == antes


def test_un_pedido_sin_sucursal_valida_contra_el_precio_de_la_sucursal(admin_client, cajero_client):
    """ADR-085: con `exigir_precio_de_sucursal` prendida, omitir `sucursal_id` no vuelve al precio general."""
    producto, _, sucursal = _escenario(admin_client)
    abrir_turno(cajero_client)
    antes = admin_client.app.state.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]

    # El precio general sin declarar la sucursal: 409 con el de la sucursal del turno, sin escribir nada.
    general = _venta(cajero_client, GENERAL, producto_id=producto)
    assert general.status_code == 409, general.text
    assert general.json()["detail"]["sucursal_id"] == sucursal
    assert [p["esperado"] for p in general.json()["detail"]["precios"]] == [DE_LA_SUCURSAL]
    assert admin_client.app.state.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == antes

    # Y el de la sucursal se cobra aunque el pedido no la nombre.
    ok = _venta(cajero_client, DE_LA_SUCURSAL, producto_id=producto)
    assert ok.status_code == 200, ok.text
    assert ok.json()["total"] == DE_LA_SUCURSAL


def test_la_sucursal_la_decide_el_deposito_de_la_venta_no_el_pedido(admin_client, cajero_client):
    """Un pedido que dice otra sucursal no cambia contra cuál se valida: el servidor usa la del depósito del turno."""
    producto, _, _ = _escenario(admin_client)
    otra = admin_client.post("/api/sucursales", json={"nombre": "Norte", "deposito": ""}).json()
    abrir_turno(cajero_client)  # en la sucursal predeterminada

    ok = _venta(cajero_client, DE_LA_SUCURSAL, producto_id=producto, sucursal_id=otra["id"])
    assert ok.status_code == 200, ok.text
    assert ok.json()["total"] == DE_LA_SUCURSAL
