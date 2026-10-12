"""El servidor valida el precio de cada línea de la venta (ADR-079; `OpcionesVentas.validar_precios` de libracommerce ADR-049).

La regla y sus casos de borde (tolerancia, vigencias, listas, el quiebre entre variantes, la balanza por importe y por peso, las
etiquetas que no valen) los prueba `libracommerce` (`tests/test_validar_precio_de_venta.py`). Acá, lo que es de este producto:

- que la opción está prendida en `app/main.py` y la ve **el cajero**, que es quien vende desde el POS;
- que un precio distinto da 409 con el cuerpo que lee `Pos.tsx` (`detail.codigo`, `detail.precios`) y **no escribe nada**
  (ni venta, ni stock, ni caja);
- que lo que el POS arma a partir de `GET /api/productos/escanear` (la etiqueta cruda y el precio o la cantidad que ésta trae)
  se cobra, y que un importe falsificado sobre la misma etiqueta no;
- que el ítem libre y el descuento manual se rechazan (el POS no manda ninguno).
"""
import pytest
from ventas_helpers import abrir_turno, con_stock, crear_item, deposito_default, hoy, stock

#: La etiqueta de la balanza del test: prefijo 20, producto 123 de la balanza y 5 dígitos de valor.
ETIQUETA_POR_IMPORTE = "2000123042004"  # $42,00 con divisor 100
ETIQUETA_POR_PESO = "2000123007504"  # 0,750 kg con divisor 1000


def _lista_default(admin, precios, quiebres=None):
    lista = admin.post("/api/listas-precio", json={"nombre": "General"}).json()
    assert admin.post(f"/api/listas-precio/{lista['id']}/set-default").status_code == 200
    r = admin.put(f"/api/listas-precio/{lista['id']}/items", json={"precios": {str(k): v for k, v in precios.items()}})
    assert r.status_code == 200, r.text
    for item_id, quiebre in (quiebres or {}).items():
        r = admin.put(f"/api/listas-precio/{lista['id']}/items/{item_id}/quiebres",
                      json={"quiebres": [{"min_quantity": quiebre[0], "amount": quiebre[1]}]})
        assert r.status_code == 200, r.text
    return lista["id"]


def _pesable(admin, nombre, precio, formato):
    """Un producto por kilo con su código en la balanza (123) y la balanza configurada como `formato`."""
    r = admin.post("/catalog/units", json={"code": "kg", "name": "Kilogramo", "allows_fraction": True, "decimal_scale": 3})
    assert r.status_code in (200, 409), r.text
    creado = admin.post("/api/productos", json={"nombre": nombre, "unidad": "kg", "precio_venta": precio})
    assert creado.status_code == 200, creado.text
    item_id = creado.json()["id"]
    assert admin.post(f"/api/productos/{item_id}/codigos", json={"tipo": "scale", "codigo": "123"}).status_code == 200
    config = {"prefix": "20", "code_digits": 5, "value_digits": 5, "total_digits": 13, **formato}
    assert admin.put("/settings/scale", json=config).status_code == 200
    return item_id


def _venta(client, items, monto=None, **extra):
    total = monto if monto is not None else sum(i["qty"] * i["precio"] for i in items)
    return client.post("/api/ventas", json={
        "fecha": hoy(), "items": items, "pagos": [{"medio": "efectivo", "monto": total}], **extra})


def _linea(item_id, qty=1, precio=100.0, **extra):
    return {"nombre": "línea", "qty": qty, "precio": precio, "producto_id": item_id, **extra}


def _filas(admin, tabla):
    return admin.app.state.conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


def test_el_cajero_vende_al_precio_del_producto(admin_client, cajero_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    abrir_turno(cajero_client)
    r = _venta(cajero_client, [_linea(item_id, 2, 100.0)])
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 200.0


def test_un_precio_manipulado_es_409_con_lo_que_lee_el_pos_y_no_escribe_nada(admin_client, cajero_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    deposito = deposito_default(admin_client)
    con_stock(admin_client, item_id, deposito, "20")
    abrir_turno(cajero_client)
    antes = {t: _filas(admin_client, t) for t in ("sales", "sale_items", "stock_movements", "caja_movimientos")}

    r = _venta(cajero_client, [_linea(item_id, 2, 1.0)])

    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    # Lo que `Pos.tsx` (`lib/precios-distintos.ts`) reconoce: el `ApiError` del kit conserva el `detail` objeto.
    assert detalle["codigo"] == "precios_distintos"
    assert detalle["mensaje"] == "Cambiaron los precios de 1 producto: revisá el total y volvé a cobrar."
    assert detalle["precios"] == [
        {"indice": 0, "producto_id": item_id, "variante_id": None, "enviado": 1.0, "esperado": 100.0}]
    assert {t: _filas(admin_client, t) for t in antes} == antes
    assert stock(admin_client, item_id, deposito) == 20


def test_con_la_lista_predeterminada_manda_el_precio_de_la_lista_y_su_quiebre_por_producto(admin_client, cajero_client):
    remera = crear_item(admin_client, "Remera", "100.00")
    _lista_default(admin_client, {remera: 100.0}, {remera: (2, 80.0)})
    talles = [admin_client.post(f"/api/productos/{remera}/variantes", json={"sku": f"REM-{t}", "nombre": t}).json()["id"]
              for t in ("M", "L")]
    abrir_turno(cajero_client)

    # Dos talles de a una unidad: juntos llegan al quiebre de 2 (lo mismo que cotiza el POS, libracommerce ADR-048).
    ok = _venta(cajero_client, [_linea(remera, 1, 80.0, variante_id=talles[0]), _linea(remera, 1, 80.0, variante_id=talles[1])])
    assert ok.status_code == 200, ok.text
    # Al precio plano del producto, con una lista que dice otra cosa: 409 con el de la lista.
    r = _venta(cajero_client, [_linea(remera, 1, 100.0, variante_id=talles[0]), _linea(remera, 1, 80.0, variante_id=talles[1])],
               monto=180.0)
    assert r.status_code == 409
    assert [(p["indice"], p["esperado"]) for p in r.json()["detail"]["precios"]] == [(0, 80.0)]


def test_la_promocion_la_sigue_calculando_el_servidor(admin_client, cajero_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    r = admin_client.post("/api/promociones", json={
        "nombre": "2x1", "tipo": "nxm", "paga": 1, "items": [{"producto_id": item_id, "cantidad": 2}]})
    assert r.status_code == 200, r.text
    abrir_turno(cajero_client)
    venta = _venta(cajero_client, [_linea(item_id, 2, 100.0)], monto=100.0)
    assert venta.status_code == 200, venta.text
    assert venta.json()["descuento"] == 100.0 and venta.json()["total"] == 100.0


def test_un_item_libre_y_un_descuento_manual_se_rechazan(admin_client, cajero_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    abrir_turno(cajero_client)
    libre = _venta(cajero_client, [{"nombre": "Suelto", "qty": 1, "precio": 10.0}])
    assert libre.status_code == 422 and "no es un producto del catálogo" in libre.json()["detail"]
    con_descuento = _venta(cajero_client, [_linea(item_id, 2, 100.0)], monto=100.0, descuento=100.0)
    assert con_descuento.status_code == 422 and "descuento manual" in con_descuento.json()["detail"]
    assert _filas(admin_client, "sales") == 0


# ── la balanza, con lo que arma el POS a partir del escaneo ──────────────


def _escanear(cajero, codigo):
    r = cajero.get("/api/productos/escanear", params={"code": codigo})
    assert r.status_code == 200, r.text
    return r.json()


def test_balanza_por_importe_se_cobra_lo_que_dice_la_etiqueta_y_un_importe_falso_no(admin_client, cajero_client):
    queso = _pesable(admin_client, "Queso", "8500", {"value_kind": "amount", "divisor": 100})
    abrir_turno(cajero_client)
    escaneado = _escanear(cajero_client, ETIQUETA_POR_IMPORTE)
    assert escaneado["de_balanza"] and escaneado["precio_unitario"] == 42.0

    # Lo que arma `Pos.tsx`: cantidad 1, el precio de la etiqueta y la etiqueta cruda.
    ok = _venta(cajero_client, [_linea(queso, 1, escaneado["precio_unitario"], etiqueta=ETIQUETA_POR_IMPORTE)])
    assert ok.status_code == 200, ok.text
    assert ok.json()["total"] == 42.0

    # El mismo paquete cobrado a otro importe: el servidor espera el de la etiqueta.
    falso = _venta(cajero_client, [_linea(queso, 1, 1.0, etiqueta=ETIQUETA_POR_IMPORTE)])
    assert falso.status_code == 409
    assert falso.json()["detail"]["precios"][0]["esperado"] == 42.0
    assert _filas(admin_client, "sales") == 1  # sólo la buena


def test_balanza_por_peso_valida_los_kilos_de_la_etiqueta(admin_client, cajero_client):
    jamon = _pesable(admin_client, "Jamón", "8000", {"value_kind": "weight", "divisor": 1000})
    abrir_turno(cajero_client)
    escaneado = _escanear(cajero_client, ETIQUETA_POR_PESO)
    assert escaneado["cantidad"] == pytest.approx(0.75)

    ok = _venta(cajero_client, [_linea(jamon, escaneado["cantidad"], 8000.0, etiqueta=ETIQUETA_POR_PESO)])
    assert ok.status_code == 200, ok.text
    assert ok.json()["total"] == 6000.0

    # Los kilos de la etiqueta son 0,750: llevarse 3 kg con esa etiqueta no se cobra.
    de_mas = _venta(cajero_client, [_linea(jamon, 3, 8000.0, etiqueta=ETIQUETA_POR_PESO)])
    assert de_mas.status_code == 422 and "no es la que dice la etiqueta" in de_mas.json()["detail"]


def test_una_etiqueta_que_no_es_de_la_balanza_del_comercio_es_422(admin_client, cajero_client):
    jamon = _pesable(admin_client, "Jamón", "8000", {"value_kind": "weight", "divisor": 1000})
    abrir_turno(cajero_client)
    r = _venta(cajero_client, [_linea(jamon, 0.75, 8000.0, etiqueta="7790123456789")])
    assert r.status_code == 422 and "no se puede leer" in r.json()["detail"]
    assert _filas(admin_client, "sales") == 0
