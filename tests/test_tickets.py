"""Ticket impreso de una venta.

El PDF lo arma LibraCore (cubierto en su propia suite); acá se prueba el
puente: que la venta de LibraCommerce llegue completa al papel y que no se
imprima lo que no corresponde.
"""
import re
import zlib
from datetime import UTC, datetime, timezone


def _abrir_turno(client):
    abierto = client.post("/shifts/open", json={"monto_inicial": 0})
    assert abierto.status_code == 200, abierto.text


def _make_item(client, name="Yerba 1kg", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _make_location(client):
    creada = client.post("/locations", json={"name": "Sucursal 1"})
    return creada.json()["id"]


def _venta_confirmada(client, cantidad="2", pagos=None, customer_id=None,
                      medio_pago=None):
    """Venta cobrada. Por defecto con `pagos`, que es como cobra el POS.

    `medio_pago` usa el atajo de un solo medio de la API, que NO deja el pago
    guardado en la venta (sólo genera el movimiento de caja).
    """
    item_id = _make_item(client)
    location_id = _make_location(client)
    _abrir_turno(client)
    borrador = client.post("/sales", json={"customer_party_id": customer_id})
    sale_id = borrador.json()["id"]
    linea = client.post(
        f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": cantidad},
    )
    cuerpo = {"location_id": location_id}
    if medio_pago:
        cuerpo["medio_pago"] = medio_pago
    else:
        cuerpo["pagos"] = pagos or [
            {"medio": "efectivo", "monto": linea.json()["total"]},
        ]
    confirmada = client.post(f"/sales/{sale_id}/confirm", json=cuerpo)
    assert confirmada.status_code == 200, confirmada.text
    return sale_id


def _texto_del_pdf(pdf: bytes) -> str:
    partes = []
    for bloque in pdf.split(b"stream")[1:]:
        crudo = bloque.split(b"endstream")[0].strip(b"\r\n")
        try:
            partes.append(zlib.decompress(crudo).decode("latin-1"))
        except (zlib.error, UnicodeDecodeError):
            partes.append(crudo.decode("latin-1", errors="ignore"))
    return "\n".join(partes)


def test_el_ticket_es_un_pdf_que_se_abre_en_pantalla(admin_client):
    sale_id = _venta_confirmada(admin_client)

    respuesta = admin_client.get(f"/sales/{sale_id}/ticket")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == "application/pdf"
    # inline y no attachment: el POS lo abre para imprimir, no lo descarga.
    assert respuesta.headers["content-disposition"].startswith("inline")
    assert respuesta.content.startswith(b"%PDF-")


def test_el_ticket_lleva_el_producto_y_el_total(admin_client):
    sale_id = _venta_confirmada(admin_client, cantidad="2")

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "Yerba 1kg" in texto
    assert "3.000,00" in texto


def test_el_ticket_lleva_el_numero_de_la_venta(admin_client):
    sale_id = _venta_confirmada(admin_client)

    numero = admin_client.get(f"/sales/{sale_id}").json()["number"]
    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert numero in texto


def test_el_ticket_nombra_al_cliente_cuando_lo_hay(admin_client):
    cliente = admin_client.post("/customers", json={"display_name": "Vecina del 12"})
    sale_id = _venta_confirmada(admin_client, customer_id=cliente.json()["id"])

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "Vecina del 12" in texto


def test_el_ticket_muestra_el_medio_de_pago(admin_client):
    sale_id = _venta_confirmada(
        admin_client, pagos=[{"medio": "tarjeta_debito", "monto": "3000"}],
    )

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    # El POS tiene medios que LibraCore no conoce: se traducen del lado de
    # VentaLibra para que no salga "tarjeta_debito" crudo en el papel.
    assert "Tarjeta de" in texto


def test_el_cobro_mixto_sale_desglosado(admin_client):
    sale_id = _venta_confirmada(admin_client, pagos=[
        {"medio": "efectivo", "monto": "1000"},
        {"medio": "mercadopago", "monto": "2000"},
    ])

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "Efectivo" in texto
    assert "Mercado Pago" in texto


def test_con_el_atajo_de_un_solo_medio_el_ticket_no_lista_pagos(admin_client):
    """Comportamiento conocido, no un bug del ticket: confirmar con
    `medio_pago` (en vez de `pagos`) registra el movimiento de caja pero no
    guarda el pago en la venta, así que no hay qué imprimir. El POS siempre
    manda `pagos`; el atajo es de la API."""
    sale_id = _venta_confirmada(admin_client, medio_pago="efectivo")

    assert admin_client.get(f"/sales/{sale_id}").json()["pagos"] == []
    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "Yerba 1kg" in texto  # el resto del ticket sale igual
    assert "Efectivo" not in texto


def test_una_venta_pesada_imprime_los_decimales(admin_client):
    """Un ticket de fiambrería tiene que decir 0,75 kg, no 1."""
    sale_id = _venta_confirmada(admin_client, cantidad="0.75")

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "0.75 x" in texto


def test_no_se_imprime_el_ticket_de_un_borrador(admin_client):
    # Un comprobante impreso de algo que todavia se puede modificar miente.
    borrador = admin_client.post("/sales", json={})
    respuesta = admin_client.get(f"/sales/{borrador.json()['id']}/ticket")
    assert respuesta.status_code == 409


def test_el_ticket_de_una_venta_inexistente_es_404(admin_client):
    assert admin_client.get("/sales/9999/ticket").status_code == 404


def test_el_ancho_del_papel_se_puede_configurar(admin_client):
    """58 y 80 mm son rollos distintos: si el ancho no llega al PDF, el
    ticket sale cortado y sólo se nota con el papel puesto."""
    sale_id = _venta_confirmada(admin_client)
    ancho_80 = admin_client.get(f"/sales/{sale_id}/ticket").content

    guardado = admin_client.put("/settings/ticket", json={
        "ancho_mm": "58", "fuente_size": 9, "mostrar_logo": False,
        "linea_corte": True, "pie": "",
    })
    assert guardado.status_code == 200, guardado.text
    ancho_58 = admin_client.get(f"/sales/{sale_id}/ticket").content

    assert b"226.77" in ancho_80  # 80mm en puntos
    assert b"164.4" in ancho_58   # 58mm


def test_el_pie_configurado_sale_impreso(admin_client):
    sale_id = _venta_confirmada(admin_client)
    admin_client.put("/settings/ticket", json={
        "ancho_mm": "80", "fuente_size": 9, "mostrar_logo": False,
        "linea_corte": True, "pie": "Gracias por su compra",
    })

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "Gracias por su compra" in texto


def test_un_ancho_de_papel_inexistente_se_rechaza(admin_client):
    respuesta = admin_client.put("/settings/ticket", json={
        "ancho_mm": "70", "fuente_size": 9, "mostrar_logo": False,
        "linea_corte": True, "pie": "",
    })
    assert respuesta.status_code == 422


def test_el_cajero_no_configura_el_ticket(staff_client):
    assert staff_client.get("/settings/ticket").status_code == 403


def test_el_ticket_se_puede_reimprimir(admin_client):
    """Se corta el papel, se traba la impresora: pedirlo de nuevo tiene que
    dar exactamente lo mismo y no alterar la venta.

    Comparar los dos PDF **no alcanza**: hasta LibraCore v1.30.0 el ticket se
    sellaba con el momento de la impresión (`/CreationDate`, con resolución de
    segundo), así que este test pasaba sólo cuando las dos requests entraban
    en el mismo segundo — y falló el 2026-08-12 en la pata de PostgreSQL del
    CI, que es más lenta. O sea que nunca había probado la reimpresión.

    Lo que lo vuelve una prueba es el sello: tiene que ser la fecha de la
    venta, que no depende del reloj del que corre el test.
    """
    sale_id = _venta_confirmada(admin_client)

    primero = admin_client.get(f"/sales/{sale_id}/ticket").content
    segundo = admin_client.get(f"/sales/{sale_id}/ticket").content
    venta = admin_client.get(f"/sales/{sale_id}").json()

    confirmada = datetime.fromisoformat(venta["confirmed_at"]).astimezone(UTC)
    sello = re.search(rb"/CreationDate\s*\(([^)]*)\)", primero)
    # Los segundos van en cero: el puente le pasa la fecha al minuto.
    assert sello and sello.group(1) == confirmada.strftime("D:%Y%m%d%H%M00Z").encode()

    assert primero == segundo
    assert venta["status"] == "confirmed"
