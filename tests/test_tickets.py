"""Ticket impreso de una venta.

El PDF lo arma LibraCore (cubierto en su propia suite); acá se prueba el
puente: que la venta de LibraCommerce llegue completa al papel y que no se
imprima lo que no corresponde.

Portado a F3 (2026-09-14, DECISIONS.md ADR-025): registrar y cobrar una venta
ya no es `POST /sales` (borrador) + `.../items` + `.../confirm` (410) -- es
una sola llamada, `POST /api/ventas` (D1). `GET /sales/{id}/ticket` en sí NO
cambió: sigue siendo la misma lectura de siempre sobre la tabla `sales`.
"""
import re
import zlib
from datetime import UTC, datetime, timedelta, timezone

from ventas_helpers import hoy

#: America/Argentina/Buenos_Aires, UTC-3 fijo -- mismo criterio que
#: `app/services/sales.py`/`app/services/tickets.py`.
_AR = timezone(timedelta(hours=-3))


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


def _venta_confirmada(client, cantidad="2", pagos=None, customer_id=None, precio="1500.00",
                      nombre="Yerba 1kg"):
    """Venta cobrada por `POST /api/ventas`, con `pagos` -- que es como cobra
    el POS. El "atajo" de un solo `medio_pago` sin línea de pago (el que
    probaba `test_con_el_atajo_de_un_solo_medio_el_ticket_no_lista_pagos`) no
    existe en la API nueva: `pagos` es obligatorio y siempre deja línea (ver
    el `xfail` de ese test, más abajo, para lo que sí quedó pendiente).

    `nombre` viaja tal cual a `sale_items.description_snapshot` -- a
    diferencia del borrador viejo, acá NO se completa solo desde el catálogo,
    así que tiene que ser el mismo nombre que `_make_item()` le puso al
    producto para que el ticket lo imprima."""
    item_id = _make_item(client, name=nombre, price=precio)
    _abrir_turno(client)
    total = float(cantidad) * float(precio)
    payload = {
        "fecha": hoy(),
        "items": [{"nombre": nombre, "qty": float(cantidad), "precio": float(precio),
                   "producto_id": item_id}],
        "pagos": pagos or [{"medio": "efectivo", "monto": total}],
    }
    if customer_id is not None:
        payload["cliente_id"] = customer_id
    venta = client.post("/api/ventas", json=payload)
    assert venta.status_code == 200, venta.text
    return venta.json()["id"]


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
        admin_client, pagos=[{"medio": "tarjeta_debito", "monto": 3000.0}],
    )

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    # El POS tiene medios que LibraCore no conoce: se traducen del lado de
    # VentaLibra para que no salga "tarjeta_debito" crudo en el papel.
    assert "Tarjeta de" in texto


def test_el_cobro_mixto_sale_desglosado(admin_client):
    sale_id = _venta_confirmada(admin_client, pagos=[
        {"medio": "efectivo", "monto": 1000.0},
        {"medio": "mercadopago", "monto": 2000.0},
    ])

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "Efectivo" in texto
    assert "Mercado Pago" in texto


def test_una_venta_nueva_lista_sus_pagos_en_el_ticket(admin_client):
    """🔴 Reemplaza a `test_con_el_atajo_de_un_solo_medio_el_ticket_no_lista_pagos`
    y a `test_una_venta_nueva_no_lista_pagos_en_el_ticket_por_ahora`.

    El primero probaba un comportamiento intencional (el atajo `medio_pago`
    sin línea de pago) que ya no existe: `POST /api/ventas` no tiene atajo,
    sólo `pagos`. El segundo documentaba el bug real de F3 -- los pagos de una
    venta nueva viven en `ventas_pagos` (LibraCore) y el puente del ticket
    leía `sale_payments` (LibraCommerce), así que `"pagos"` daba `[]` -- ya
    resuelto en `app/services/sales.py::SaleService._con_pagos_y_fecha`.
    """
    sale_id = _venta_confirmada(admin_client)

    pagos = admin_client.get(f"/sales/{sale_id}").json()["pagos"]
    assert len(pagos) == 1
    assert pagos[0]["medio"] == "efectivo"
    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "Yerba 1kg" in texto
    assert "Efectivo" in texto


def test_una_venta_pesada_imprime_los_decimales(admin_client):
    """Un ticket de fiambrería tiene que decir 0,75 kg, no 1."""
    sale_id = _venta_confirmada(admin_client, cantidad="0.75")

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert "0.75 x" in texto


def test_no_se_imprime_el_ticket_de_un_borrador(admin_client):
    """Un comprobante impreso de algo que todavia se puede modificar miente.

    🔴 `POST /sales` (que armaba el borrador) es 410 desde F3: no hay más
    forma de crear uno por HTTP, porque `POST /api/ventas` (D1) registra la
    venta completa y nunca nace en estado `draft`. El estado sigue existiendo
    en el schema -- lo tienen ventas de antes de F3 (el plan midió 3 en dev y
    1 en demo, "borradores abandonados") -- así que el chequeo del ticket
    sigue haciendo falta para esas. Se inserta directo, documentado como
    excepción: no queda ningún endpoint que deje una venta en ese estado.
    """
    conn = admin_client.app.state.conn
    cur = conn.execute("INSERT INTO sales (number) VALUES ('POS-BORRADOR-TEST')")
    conn.commit()
    sale_id = cur.lastrowid
    respuesta = admin_client.get(f"/sales/{sale_id}/ticket")
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
    # 🔴 El sello son los DÍGITOS de Argentina leídos como si fueran UTC, no
    # el instante real en UTC. `libracore.pdf_generator` usa el MISMO string
    # para lo que se IMPRIME y para `/CreationDate` (`fijar_fecha_documento`):
    # ni `fmt_fecha` ni `fecha_de_documento` convierten ninguna zona, sólo
    # reordenan texto o leen uno sin zona como UTC. Como `app/services/
    # tickets.py` arma ese string convertido a hora de Argentina (para que lo
    # IMPRESO sea correcto, que es lo que ve el cliente), el sello queda
    # corrido de la hora UTC real -- a propósito: no hay forma de tener las
    # dos cosas bien con un solo string, y gana lo impreso. Los segundos van
    # en cero: el puente le pasa la fecha al minuto.
    assert sello and sello.group(1) == confirmada.astimezone(_AR).strftime("D:%Y%m%d%H%M00Z").encode()

    assert primero == segundo
    assert venta["status"] == "confirmed"


# ── Zona horaria de `confirmed_at`: revisión del orquestador ─────────────
#
# `SaleService._con_pagos_y_fecha` reconstruye `confirmed_at` para una venta
# nueva (D1: `crear_venta_directa` sólo llena `occurred_on`). La primera
# versión lo etiquetaba `UTC` -- corría el instante 3 horas para cualquier
# consumidor que sí convierte por zona (`frontend/src/lib/fechas.ts`). Estos
# tres tests fijan el contrato correcto; los dos de abajo son las mutaciones
# que el orquestador pidió ejercitar (revertidas después de medir).


def test_una_venta_nueva_tiene_el_offset_de_argentina_no_utc(admin_client):
    """El bug real: `confirmed_at` reconstruido con offset `+00:00` en vez de
    `-03:00`. `GET /sales/{id}` tiene que devolver el instante VERDADERO --
    con el offset real -- para que un consumidor que convierte por zona
    (el frontend) muestre la hora local correcta y no una corrida 3 horas.

    `_venta_confirmada()` manda `hoy()` (la fecha real de Argentina, no una
    fecha fija) en el payload, así que comparar contra `datetime.now(_AR)` ya
    no es frágil -- antes, con `"fecha": "2026-09-14"` fija, esta comparación
    se rompió apenas la sesión cruzó la medianoche real del 2026-09-15, sin
    que el código tuviera ningún bug (ver `tests/ventas_helpers.py::hoy`)."""
    sale_id = _venta_confirmada(admin_client)
    venta = admin_client.get(f"/sales/{sale_id}").json()
    confirmado = datetime.fromisoformat(venta["confirmed_at"])
    assert confirmado.utcoffset() == timedelta(hours=-3), venta["confirmed_at"]
    assert abs(confirmado.astimezone(_AR) - datetime.now(_AR)) < timedelta(minutes=5)


def test_el_ticket_de_una_venta_vieja_imprime_hora_de_argentina():
    """🔴 Bug de producción PREEXISTENTE que este arreglo tapa de paso: una
    venta vieja guarda `confirmed_at` en UTC real (`datetime.now(UTC)`, el
    `confirm_sale` legado). `libracore.ticket_generator.fmt_fecha` no
    convierte ninguna zona -- imprime los dígitos que le llegan tal cual --
    así que sin convertir a Argentina ANTES de armar el string, el ticket de
    cualquier venta vieja sale con la hora UTC cruda, 3 horas adelantada."""
    from app.services.tickets import ticket_de_venta

    class _Linea:
        description_snapshot = "Yerba 1kg"
        quantity = 2
        unit_price = 5500

    class _Pago:
        method = "efectivo"
        amount = 11000

    class _VentaVieja:
        number = "0001-00000042"
        confirmed_at = datetime(2026, 3, 11, 15, 30, tzinfo=UTC)  # UTC real
        items = [_Linea()]
        discount_total = 0
        total = 11000
        payments = [_Pago()]

    texto = _texto_del_pdf(ticket_de_venta(_VentaVieja()))
    assert "11-03-2026 12:30" in texto


def test_el_ticket_de_una_venta_nueva_imprime_la_hora_local(admin_client):
    """El ticket y `GET /sales/{id}` tienen que coincidir en qué hora fue la
    venta -- ambos parten del mismo `confirmed_at` reconstruido, por
    caminos de lectura distintos (`SaleService.get()` cada vez)."""
    sale_id = _venta_confirmada(admin_client)
    venta = admin_client.get(f"/sales/{sale_id}").json()
    confirmado = datetime.fromisoformat(venta["confirmed_at"])
    esperado = confirmado.astimezone(_AR).strftime("%d-%m-%Y %H:%M")

    texto = _texto_del_pdf(admin_client.get(f"/sales/{sale_id}/ticket").content)
    assert esperado in texto
