"""El recibo de la cobranza: el papel que se lleva el que vino a pagar.

Hasta `libracore v1.9.0` cobrar una deuda no emitía nada. Acá se prueba el
cableado del producto, no la lógica de emisión (eso está en la suite del
motor): que el cobro emita solo, que el PDF salga por HTTP, y que el pago
siga siendo válido aunque el comprobante falle.

**El test que más importa es `test_el_cobro_emite_el_recibo_solo`.**
`registrar_cobranza` atrapa cualquier excepción de la emisión a propósito
—perder el comprobante es molesto, perder el pago es plata— así que si el
cableado estuviera roto **la suite entera pasaría igual** y `recibo_id`
volvería en `None` sin que nada se queje. Afirmarlo es lo único que
distingue "anda" de "no explota".

Desde la fase 14 (ADR-040) `/api/recibos` es `libracore.recibos_router.
build_recibos_router`, el mismo de Contalibra, con `get_venta=db_ventas.
get_venta` (las ventas de mostrador viven en `sales` de LibraCommerce). Gana
de paso listar/detalle, emitir de venta y anular (sólo admin) -- se prueban
al final del archivo.
"""
import io

from libracore.db import recibos as db_recibos
from pypdf import PdfReader
from ventas_helpers import caja_default, hoy


def _abrir_turno(client, monto_inicial=0):
    abierto = client.post(
        "/api/turnos/abrir", json={"monto_inicial": monto_inicial, "caja_id": caja_default(client)}
    )
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["id"]


def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post(
        "/api/productos",
        json={"nombre": name, "unidad": "u", "precio_venta": price},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _deudor(client, nombre="Vecina del 12", cantidad="2"):
    """Cliente con deuda real: la venta fiada es la que la genera.

    Portado a F3 (2026-09-14, DECISIONS.md ADR-025): fiar ya no es
    `POST /sales` (borrador) + `.../items` + `.../confirm` con
    `medio_pago=cuenta_corriente` (410) -- es `POST /api/ventas` (D1) con
    `cliente_id` y un pago `cuenta_corriente` (D3: ese pago ES la deuda, no
    hace falta un `cc_debito` aparte)."""
    item_id = _make_item(client)
    cliente_id = client.post("/api/clientes", json={"name": nombre}).json()["id"]
    _abrir_turno(client)

    precio = 1500.0
    total = float(cantidad) * precio
    confirmada = client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": float(cantidad), "precio": precio,
                   "producto_id": item_id}],
        "pagos": [{"medio": "cuenta_corriente", "monto": total}],
        "cliente_id": cliente_id,
    })
    assert confirmada.status_code == 200, confirmada.text
    return cliente_id


def _texto_del_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(contenido)).pages)


# ── La emisión ───────────────────────────────────────────────────────────────

def test_el_cobro_emite_el_recibo_solo(admin_client):
    """Sin esta afirmación, un cableado roto pasa desapercibido: la emisión
    está dentro de un `except Exception` que no rompe el cobro."""
    cliente_id = _deudor(admin_client, "Emite solo")
    resp = admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                             json={"fecha": hoy(), "monto": "1000.00", "medio_pago": "efectivo"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["recibo_id"] is not None


def test_el_recibo_sale_a_nombre_del_cliente_y_por_el_monto_cobrado(admin_client):
    cliente_id = _deudor(admin_client, "Panaderia Sol")
    recibo_id = admin_client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"fecha": hoy(), "monto": "1200.50", "medio_pago": "transferencia",
              "referencia": "transf 771"}).json()["recibo_id"]

    # La ruta del kit sólo devuelve el id (idempotente): el contenido se lee del recibo.
    emitido = admin_client.post(f"/api/recibos/cobranza/{_pago_de(admin_client, cliente_id)}").json()
    assert emitido["id"] == recibo_id
    recibo = db_recibos.get_recibo(recibo_id)
    assert f"{str(recibo['punto_venta']).zfill(4)}-{str(recibo['numero']).zfill(8)}" == "0001-00000001"
    assert recibo["cliente_razon"] == "Panaderia Sol"
    assert float(recibo["total"]) == 1200.50
    assert not recibo["anulado"]


def _pago_de(client, party_id):
    """El `cc_pago_id` del último abono de la cuenta."""
    cuenta = client.get(f"/api/cuenta-corriente/{party_id}").json()
    abonos = [m["cc_pago_id"] for m in cuenta["movimientos"] if m["cc_pago_id"]]
    assert abonos, "la cuenta no tiene abonos con cc_pago_id"
    return abonos[-1]


def test_los_movimientos_traen_el_id_del_pago_para_poder_ofrecer_el_recibo(admin_client):
    """Los cargos NO lo traen: un cargo no es plata que entró, no hay recibo
    que emitirle."""
    cliente_id = _deudor(admin_client, "Con abonos")
    admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                      json={"fecha": hoy(), "monto": "500.00", "medio_pago": "efectivo"})

    movimientos = admin_client.get(f"/api/cuenta-corriente/{cliente_id}").json()["movimientos"]
    cargos = [m for m in movimientos if m["tipo"] == "debito"]
    abonos = [m for m in movimientos if m["tipo"] == "credito"]
    assert all(m["cc_pago_id"] is None for m in cargos)
    assert all(m["cc_pago_id"] is not None for m in abonos)


def test_pedir_el_recibo_dos_veces_no_emite_dos(admin_client):
    """El botón de la pantalla llama sin saber si ya existe."""
    cliente_id = _deudor(admin_client, "Idempotente")
    admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                      json={"fecha": hoy(), "monto": "800.00", "medio_pago": "efectivo"})
    pago_id = _pago_de(admin_client, cliente_id)

    primero = admin_client.post(f"/api/recibos/cobranza/{pago_id}").json()
    segundo = admin_client.post(f"/api/recibos/cobranza/{pago_id}").json()
    assert primero["id"] == segundo["id"]


def test_dos_cobros_son_dos_recibos_correlativos(admin_client):
    cliente_id = _deudor(admin_client, "Paga en cuotas", cantidad="4")
    a = admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                          json={"fecha": hoy(), "monto": "1000.00", "medio_pago": "efectivo"}).json()
    b = admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                          json={"fecha": hoy(), "monto": "2000.00", "medio_pago": "efectivo"}).json()
    assert a["recibo_id"] != b["recibo_id"]


def test_un_pago_que_no_existe_no_emite_recibo(admin_client):
    # 409, no 404: mismo criterio que Contalibra (fase 14, ADR-040) -- antes de adoptar el router del
    # motor, este endpoint propio contestaba 404 para el mismo caso.
    assert admin_client.post("/api/recibos/cobranza/99999").status_code == 409


# ── El PDF ───────────────────────────────────────────────────────────────────

def test_el_pdf_sale_por_http_con_los_datos_del_cobro(admin_client):
    cliente_id = _deudor(admin_client, "Ferreteria Luna")
    recibo_id = admin_client.post(
        f"/api/cuenta-corriente/{cliente_id}/pagar",
        json={"fecha": hoy(), "monto": "1500.00", "medio_pago": "transferencia",
              "referencia": "transf 991"}).json()["recibo_id"]

    resp = admin_client.get(f"/api/recibos/{recibo_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    texto = _texto_del_pdf(resp.content)
    assert "0001-00000001" in texto
    assert "Ferreteria Luna" in texto
    assert "1.500,00" in texto
    assert "transf 991" in texto


def test_reimprimir_devuelve_el_mismo_papel(admin_client):
    cliente_id = _deudor(admin_client, "Reimprime")
    recibo_id = admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                                  json={"fecha": hoy(), "monto": "1000.00"}).json()["recibo_id"]
    primero = admin_client.get(f"/api/recibos/{recibo_id}/pdf").content
    segundo = admin_client.get(f"/api/recibos/{recibo_id}/pdf").content
    assert primero == segundo


def test_un_recibo_que_no_existe_da_404(admin_client):
    assert admin_client.get("/api/recibos/99999/pdf").status_code == 404


# ── El cobro manda sobre el comprobante ──────────────────────────────────────

def test_si_falla_la_emision_el_cobro_igual_queda_registrado(admin_client, monkeypatch):
    """La regla: perder el comprobante es molesto, perder el pago es plata.
    Se rompe la emisión a propósito y se verifica que el saldo igual baje."""
    cliente_id = _deudor(admin_client, "Cobro a salvo")
    saldo_antes = float(admin_client.get(f"/api/cuenta-corriente/{cliente_id}").json()["saldo"])

    import libracore.recibos as mod  # el router del motor importa `emitir_recibo_cobranza` al cobrar

    def _explota(*a, **kw):
        raise RuntimeError("la emision se rompio")

    monkeypatch.setattr(mod, "emitir_recibo_cobranza", _explota)

    resp = admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                             json={"fecha": hoy(), "monto": "1000.00", "medio_pago": "efectivo"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["recibo_id"] is None
    assert float(resp.json()["saldo"]) == saldo_antes - 1000.0


def test_despues_de_un_fallo_el_boton_puede_emitirlo(admin_client, monkeypatch):
    """Por eso el endpoint de emisión existe aparte del cobro."""
    cliente_id = _deudor(admin_client, "Reintento")
    import libracore.recibos as mod
    monkeypatch.setattr(mod, "emitir_recibo_cobranza",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar", json={"fecha": hoy(), "monto": "1000.00"})
    monkeypatch.undo()

    recibo = admin_client.post(f"/api/recibos/cobranza/{_pago_de(admin_client, cliente_id)}")
    assert recibo.status_code == 200
    reintentado = db_recibos.get_recibo(recibo.json()["id"])
    assert f"{str(reintentado['punto_venta']).zfill(4)}-{str(reintentado['numero']).zfill(8)}" == "0001-00000001"


# ── Lo que se gana con el router del motor (fase 14, ADR-040) ────────────────

def test_listar_trae_los_recibos_emitidos(admin_client):
    cliente_id = _deudor(admin_client, "Listado")
    admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                      json={"fecha": hoy(), "monto": "300.00", "medio_pago": "efectivo"})

    listado = admin_client.get("/api/recibos").json()
    assert listado["total"] >= 1
    assert any(r["cliente_id"] == cliente_id for r in listado["recibos"])


def test_emitir_recibo_de_una_venta_de_mostrador(admin_client):
    """El gancho `get_venta` en acción: la venta sale de `sales`
    (LibraCommerce), no de `ventas` (la tabla del propio esquema del motor,
    que en este producto está vacía)."""
    item_id = _make_item(admin_client, "Gaseosa")
    _abrir_turno(admin_client)
    venta = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 1, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "efectivo", "monto": 1500.0}],
    }).json()

    r = admin_client.post(f"/api/recibos/venta/{venta['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["origen_tipo"] == "venta"
    assert r.json()["total"] == 1500.0


def test_una_venta_inexistente_no_emite_recibo(admin_client):
    assert admin_client.post("/api/recibos/venta/99999").status_code == 409


def test_un_cajero_no_puede_anular_un_recibo(staff_client, admin_client):
    cliente_id = _deudor(admin_client, "Sin anular")
    recibo_id = admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                                  json={"fecha": hoy(), "monto": "100.00"}).json()["recibo_id"]
    assert staff_client.post(f"/api/recibos/{recibo_id}/anular", json={"motivo": "x"}).status_code == 403


def test_un_admin_puede_anular_un_recibo(admin_client):
    cliente_id = _deudor(admin_client, "Anulable")
    recibo_id = admin_client.post(f"/api/cuenta-corriente/{cliente_id}/pagar",
                                  json={"fecha": hoy(), "monto": "100.00"}).json()["recibo_id"]
    r = admin_client.post(f"/api/recibos/{recibo_id}/anular", json={"motivo": "error de carga"})
    assert r.status_code == 200, r.text
    assert r.json()["anulado"] is True
