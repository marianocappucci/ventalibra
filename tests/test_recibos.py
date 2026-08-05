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
"""
import io

from pypdf import PdfReader


def _abrir_turno(client, monto_inicial=0):
    abierto = client.post("/shifts/open", json={"monto_inicial": monto_inicial})
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["turno"]["id"]


def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _make_location(client, name="Sucursal 1"):
    creada = client.post("/locations", json={"name": name})
    assert creada.status_code == 200, creada.text
    return creada.json()["id"]


def _deudor(client, nombre="Vecina del 12", cantidad="2"):
    """Cliente con deuda real: la venta fiada es la que la genera."""
    item_id = _make_item(client)
    location_id = _make_location(client)
    cliente_id = client.post("/customers", json={"display_name": nombre}).json()["id"]
    _abrir_turno(client)

    borrador = client.post("/sales", json={"customer_party_id": cliente_id})
    sale_id = borrador.json()["id"]
    client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": cantidad})
    confirmada = client.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "cuenta_corriente"},
    )
    assert confirmada.status_code == 200, confirmada.text
    return cliente_id


def _texto_del_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(contenido)).pages)


# ── La emisión ───────────────────────────────────────────────────────────────

def test_el_cobro_emite_el_recibo_solo(admin_client):
    """Sin esta afirmación, un cableado roto pasa desapercibido: la emisión
    está dentro de un `except Exception` que no rompe el cobro."""
    cliente_id = _deudor(admin_client, "Emite solo")
    resp = admin_client.post(f"/accounts/{cliente_id}/payments",
                             json={"monto": "1000.00", "medio_pago": "efectivo"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["recibo_id"] is not None


def test_el_recibo_sale_a_nombre_del_cliente_y_por_el_monto_cobrado(admin_client):
    cliente_id = _deudor(admin_client, "Panaderia Sol")
    recibo_id = admin_client.post(
        f"/accounts/{cliente_id}/payments",
        json={"monto": "1200.50", "medio_pago": "transferencia",
              "referencia": "transf 771"}).json()["recibo_id"]

    recibo = admin_client.post(f"/accounts/receipts/{_pago_de(admin_client, cliente_id)}").json()
    assert recibo["id"] == recibo_id
    assert recibo["numero_visible"] == "0001-00000001"
    assert recibo["cliente_razon"] == "Panaderia Sol"
    # Numérico, no textual: el Decimal serializa sin el cero final ("1200.5").
    assert float(recibo["total"]) == 1200.50
    assert recibo["anulado"] is False


def _pago_de(client, party_id):
    """El `cc_pago_id` del último abono de la cuenta."""
    cuenta = client.get(f"/accounts/{party_id}").json()
    abonos = [m["cc_pago_id"] for m in cuenta["movimientos"] if m["cc_pago_id"]]
    assert abonos, "la cuenta no tiene abonos con cc_pago_id"
    return abonos[-1]


def test_los_movimientos_traen_el_id_del_pago_para_poder_ofrecer_el_recibo(admin_client):
    """Los cargos NO lo traen: un cargo no es plata que entró, no hay recibo
    que emitirle."""
    cliente_id = _deudor(admin_client, "Con abonos")
    admin_client.post(f"/accounts/{cliente_id}/payments",
                      json={"monto": "500.00", "medio_pago": "efectivo"})

    movimientos = admin_client.get(f"/accounts/{cliente_id}").json()["movimientos"]
    cargos = [m for m in movimientos if m["tipo"] == "debito"]
    abonos = [m for m in movimientos if m["tipo"] == "credito"]
    assert all(m["cc_pago_id"] is None for m in cargos)
    assert all(m["cc_pago_id"] is not None for m in abonos)


def test_pedir_el_recibo_dos_veces_no_emite_dos(admin_client):
    """El botón de la pantalla llama sin saber si ya existe."""
    cliente_id = _deudor(admin_client, "Idempotente")
    admin_client.post(f"/accounts/{cliente_id}/payments",
                      json={"monto": "800.00", "medio_pago": "efectivo"})
    pago_id = _pago_de(admin_client, cliente_id)

    primero = admin_client.post(f"/accounts/receipts/{pago_id}").json()
    segundo = admin_client.post(f"/accounts/receipts/{pago_id}").json()
    assert primero["id"] == segundo["id"]


def test_dos_cobros_son_dos_recibos_correlativos(admin_client):
    cliente_id = _deudor(admin_client, "Paga en cuotas", cantidad="4")
    a = admin_client.post(f"/accounts/{cliente_id}/payments",
                          json={"monto": "1000.00", "medio_pago": "efectivo"}).json()
    b = admin_client.post(f"/accounts/{cliente_id}/payments",
                          json={"monto": "2000.00", "medio_pago": "efectivo"}).json()
    assert a["recibo_id"] != b["recibo_id"]


def test_un_pago_que_no_existe_no_emite_recibo(admin_client):
    assert admin_client.post("/accounts/receipts/99999").status_code == 404


# ── El PDF ───────────────────────────────────────────────────────────────────

def test_el_pdf_sale_por_http_con_los_datos_del_cobro(admin_client):
    cliente_id = _deudor(admin_client, "Ferreteria Luna")
    recibo_id = admin_client.post(
        f"/accounts/{cliente_id}/payments",
        json={"monto": "1500.00", "medio_pago": "transferencia",
              "referencia": "transf 991"}).json()["recibo_id"]

    resp = admin_client.get(f"/accounts/receipts/{recibo_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    texto = _texto_del_pdf(resp.content)
    assert "0001-00000001" in texto
    assert "Ferreteria Luna" in texto
    assert "1.500,00" in texto
    assert "transf 991" in texto


def test_reimprimir_devuelve_el_mismo_papel(admin_client):
    cliente_id = _deudor(admin_client, "Reimprime")
    recibo_id = admin_client.post(f"/accounts/{cliente_id}/payments",
                                  json={"monto": "1000.00"}).json()["recibo_id"]
    primero = admin_client.get(f"/accounts/receipts/{recibo_id}/pdf").content
    segundo = admin_client.get(f"/accounts/receipts/{recibo_id}/pdf").content
    assert primero == segundo


def test_un_recibo_que_no_existe_da_404(admin_client):
    assert admin_client.get("/accounts/receipts/99999/pdf").status_code == 404


# ── El cobro manda sobre el comprobante ──────────────────────────────────────

def test_si_falla_la_emision_el_cobro_igual_queda_registrado(admin_client, monkeypatch):
    """La regla: perder el comprobante es molesto, perder el pago es plata.
    Se rompe la emisión a propósito y se verifica que el saldo igual baje."""
    cliente_id = _deudor(admin_client, "Cobro a salvo")
    saldo_antes = float(admin_client.get(f"/accounts/{cliente_id}").json()["saldo"])

    import app.services.cuenta_corriente as mod

    def _explota(*a, **kw):
        raise RuntimeError("la emision se rompio")

    monkeypatch.setattr(mod, "emitir_recibo_cobranza", _explota)

    resp = admin_client.post(f"/accounts/{cliente_id}/payments",
                             json={"monto": "1000.00", "medio_pago": "efectivo"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["recibo_id"] is None
    assert float(resp.json()["saldo"]) == saldo_antes - 1000.0


def test_despues_de_un_fallo_el_boton_puede_emitirlo(admin_client, monkeypatch):
    """Por eso el endpoint de emisión existe aparte del cobro."""
    cliente_id = _deudor(admin_client, "Reintento")
    import app.services.cuenta_corriente as mod
    monkeypatch.setattr(mod, "emitir_recibo_cobranza",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    admin_client.post(f"/accounts/{cliente_id}/payments", json={"monto": "1000.00"})
    monkeypatch.undo()

    recibo = admin_client.post(f"/accounts/receipts/{_pago_de(admin_client, cliente_id)}")
    assert recibo.status_code == 200
    assert recibo.json()["numero_visible"] == "0001-00000001"
