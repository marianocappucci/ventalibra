"""Facturación desde una venta: hoy pasa por `/api/ventas` (la capa ERP de
LibraCommerce, F3 del plan post-P9, ver DECISIONS.md ADR-025).

Portado desde el modelo viejo (`POST /sales/{id}/confirm` con `invoice: bool`,
que confirmaba y facturaba en la misma llamada, con IVA fijo al 21%): ahora
`POST /api/ventas` registra la venta completa en una sola llamada (D1) y
`POST /api/ventas/{vid}/facturar` es un paso aparte (D2/D6, `libracore.
venta_facturacion`, montado como `libracore.ventas_cobro_router` en
`app/main.py`).

🔴 **Lo que cambió de verdad, no sólo de ruta**: la alícuota. El motor nuevo
no tiene el 21% fijo de `app/services/billing.py` (que queda vivo pero sólo
para el camino LEGADO, de sólo lectura desde F3) -- usa las de
`libracore.venta_facturacion`, que default a Monotributista/Factura C sin
discriminar IVA cuando la instancia no configuró su propia condición de IVA
(`empresa_iva_condition`, `PUT /api/config/empresa`). Es la corrección que
menciona el plan post-P9 (sección "Lo que este ADR NO hace" de ADR-025): antes
facturaba tipo B con IVA discriminado aunque el emisor fuera monotributista,
que no es correcto.
"""
from libracore.db import caja as db_caja
from ventas_helpers import caja_default, hoy


def _make_location(client):
    """Compat para los tests de otros archivos que todavía importan esto de
    acá (`test_la_factura_declara_su_ambiente.py`, `test_medios_elegibles.py`).
    `POST /api/ventas` no recibe depósito: devuelve el default que
    `app/db.py::connect()` siembra (ver `tests/test_devoluciones.py`, que
    tiene el mismo comentario más largo)."""
    conn = client.app.state.conn
    return conn.execute("SELECT id FROM locations WHERE is_default = 1 LIMIT 1").fetchone()[0]


class _RespuestaConFactura:
    """Envoltorio para que `_confirmed_sale(..., invoice=True)` siga
    devolviendo `.json()["factura"]` como en el modelo viejo, aunque ahora
    sean dos llamadas HTTP (`POST /api/ventas` + `POST .../facturar`)."""

    def __init__(self, venta_response, factura: dict | None):
        self._venta_response = venta_response
        self._factura = factura

    @property
    def status_code(self):
        return self._venta_response.status_code

    @property
    def text(self):
        return self._venta_response.text

    def json(self):
        return {**self._venta_response.json(), "factura": self._factura}


def _confirmed_sale(client, item_id, location_id=None, quantity="1",  # noqa: ARG001
                    medio_pago="efectivo", invoice=False, **_ignorados):
    """Compat con el modelo viejo (`POST /sales` borrador + `POST .../confirm`,
    que abría el turno solo) para los tests de otros archivos que todavía la
    importan de acá. Registra la venta completa en una sola llamada (D1) y,
    si `invoice=True`, factura aparte (D2/D6) -- ver el docstring del módulo.
    """
    if client.get("/shifts/current").json().get("turno") is None:
        client.post(
            "/shifts/open", json={"monto_inicial": 0, "caja_id": caja_default(client)}
        )
    venta = _registrar_venta(client, item_id, medio=medio_pago, monto=float(quantity) * 1500.0)
    factura = None
    if invoice and venta.status_code == 200:
        vid = venta.json()["id"]
        factura = client.post(f"/api/ventas/{vid}/facturar").json().get("factura")
    return _RespuestaConFactura(venta, factura)


def _abrir_turno(client, monto_inicial=0):
    """Sin turno abierto, registrar una venta da 409: una venta fuera de
    turno sería plata sin control de caja."""
    abierto = client.post(
        "/shifts/open", json={"monto_inicial": monto_inicial, "caja_id": caja_default(client)}
    )
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["turno"]["id"]


def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price, "default_cost": "900.00"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _registrar_venta(client, item_id, *, cliente_id=None, cliente_nombre="",
                     precio="1500.00", medio="efectivo", monto=None):
    """Arma y registra una venta de una línea, en una sola llamada (D1). El
    turno tiene que estar abierto antes: lo abre el caller."""
    monto = float(precio) if monto is None else monto
    payload = {
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 1, "precio": float(precio), "producto_id": item_id}],
        "pagos": [{"medio": medio, "monto": monto}],
    }
    if cliente_id is not None:
        payload["cliente_id"] = cliente_id
        payload["cliente_nombre"] = cliente_nombre
    return client.post("/api/ventas", json=payload)


def test_get_arca_config_defaults_to_none(admin_client):
    response = admin_client.get("/config/arca")
    assert response.status_code == 200
    assert response.json() is None


def test_set_and_get_arca_config(admin_client):
    """🔴 La fila se crea con `venta`, que es el slug con el que
    `services/billing.py` lee la configuracion de facturacion (el camino
    LEGADO -- `libracore.venta_facturacion` no usa `db_arca_config` por
    empresa: resuelve el punto de venta con `resolver_punto_venta`, ver
    `app/db_ventas.py`)."""
    created = admin_client.put("/config/arca", json={
        "cuit": "30-12345678-9", "punto_venta": 1,
    })
    assert created.status_code == 200, created.text
    assert created.json()["empresa"] == "venta"

    fetched = admin_client.get("/config/arca")
    assert fetched.json()["cuit"] == "30-12345678-9"


def test_el_certificado_se_sube_y_se_valida_antes_de_escribirlo(admin_client):
    """Subir el `.csr` --el pedido-- en vez del `.crt` que ARCA devuelve es el
    error habitual, y antes se aceptaba: el router propio escribia el path que
    le mandaran sin mirar nada, y fallaba recien al emitir."""
    r = admin_client.post(
        "/config/arca/certificado",
        files={"archivo": ("pedido.pem", b"-----BEGIN CERTIFICATE REQUEST-----", "text/plain")},
    )
    assert r.status_code == 422
    assert "certificado" in r.json()["detail"].lower()


def test_el_estado_dice_si_la_instancia_puede_facturar(admin_client):
    """🔑 Trae el vencimiento del certificado, que es el dato que evita la falla
    silenciosa: duran dos anos y el dia que vencen la facturacion deja de andar
    sin que nadie haya tocado nada."""
    r = admin_client.get("/config/arca/estado")
    assert r.status_code == 200
    assert r.json()["configurado"] is False


def test_registrar_una_venta_no_la_factura_sola(admin_client):
    """Registrar la venta (D1) nunca factura: facturar es `POST .../facturar`,
    un paso aparte y explícito."""
    item_id = _make_item(admin_client)
    _abrir_turno(admin_client)
    venta = _registrar_venta(admin_client, item_id)
    assert venta.status_code == 200, venta.text
    assert venta.json()["factura_id"] is None


def test_facturar_sin_cliente_factura_a_consumidor_final(admin_client):
    """Sin `empresa_iva_condition` configurada, el emisor es Monotributista
    por default y factura tipo C -- sin discriminar IVA. Es la corrección
    documentada en ADR-025: antes de esto, este producto facturaba tipo B con
    IVA discriminado aunque el emisor fuera monotributista."""
    item_id = _make_item(admin_client, price="1000.00")
    _abrir_turno(admin_client)
    venta = _registrar_venta(admin_client, item_id, precio="1000.00")
    vid = venta.json()["id"]

    facturada = admin_client.post(f"/api/ventas/{vid}/facturar")
    assert facturada.status_code == 200, facturada.text
    factura = facturada.json()["factura"]
    assert factura["cliente_razon"] == "Consumidor Final"
    assert factura["tipo"] == 11  # factura C: monotributista, sin discriminar IVA
    assert factura["cae"] is not None  # mock de dev, ver arca_facturacion.get_next_numero_with_arca


def test_facturar_a_un_responsable_inscripto_usa_los_datos_de_ese_cliente(admin_client):
    """Factura A: el emisor RI factura a un RI con SUS datos y no con los de otro cliente.

    `libracore.venta_facturacion.facturar_venta` resuelve el cliente con `db_clients.get_client(
    venta["cliente_id"])`. Hasta la migración `0004` (2026-09-26) `cliente_id` era un `party_id` que
    NO coincidía con el `clients.id`, y hacía falta un puente por `external_ref` (este test armaba
    la colisión a propósito). Con la convención del motor -- cliente = party de igual id -- el id
    de la venta ES el del cliente; lo que se prueba ahora es que con **dos clientes** se factura
    al correcto.
    """
    admin_client.put("/api/config/empresa", json={"empresa_iva_condition": "Responsable Inscripto"})
    otro = admin_client.post("/api/clientes", json={"name": "Cliente Equivocado"})
    assert otro.status_code == 200, otro.text
    empresa = admin_client.post("/api/clientes", json={
        "name": "Empresa SA", "cuit_dni": "30-99999999-1", "iva_condition": "Responsable Inscripto",
    })
    assert empresa.status_code == 200, empresa.text
    customer_id = empresa.json()["id"]
    assert customer_id != otro.json()["id"]

    item_id = _make_item(admin_client)
    _abrir_turno(admin_client)
    venta = _registrar_venta(
        admin_client, item_id, cliente_id=customer_id, cliente_nombre="Empresa SA",
        medio="tarjeta_credito",
    )
    assert venta.status_code == 200, venta.text
    vid = venta.json()["id"]

    facturada = admin_client.post(f"/api/ventas/{vid}/facturar")
    assert facturada.status_code == 200, facturada.text
    factura = facturada.json()["factura"]
    # Factura A: RI factura a RI, con los datos de ese cliente.
    assert factura["tipo"] == 1
    assert factura["cliente_razon"] == "Empresa SA"
    assert factura["cliente_cuit"] == "30-99999999-1"


def test_registrar_una_venta_siempre_registra_un_movimiento_de_caja(admin_client):
    item_id = _make_item(admin_client, price="500.00")
    _abrir_turno(admin_client)

    before = len(db_caja.get_caja_movimientos())
    venta = _registrar_venta(admin_client, item_id, precio="500.00")
    assert venta.status_code == 200, venta.text
    numero = venta.json()["numero"]

    movimientos = db_caja.get_caja_movimientos()
    assert len(movimientos) == before + 1
    assert numero in movimientos[0]["concepto"]
    assert movimientos[0]["factura_id"] is None
    assert float(movimientos[0]["monto"]) == 500.0
