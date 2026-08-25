"""El vocabulario de medios de pago en este producto.

🔴 **Este POS ya usa casi todo el vocabulario canónico.** `efectivo`,
`transferencia`, `tarjeta_debito`, `tarjeta_credito` y `cuenta_corriente` son
exactamente las claves de la familia — de hecho VentaLibra fue quien partió la
tarjeta en dos, y por eso la lista canónica la partió también.

Lo único que diverge es **`mercado_pago` con guión bajo**, y eso **no se
normaliza acá**: hay ventas y movimientos de caja escritos con esa grafía.
Cambiar la escritura sin migrar los datos parte cada reporte en dos filas para
la misma cosa. El orden es *primero los datos, después la grafía* — la
migración va en su propio PR, y `medios_pago.HISTORICOS` la sabe leer mientras
tanto.
"""
from libracore import medios_pago

from app.routers import sales
from app.services import tickets


def test_los_medios_del_pos_son_los_de_la_familia():
    """Los cinco que este POS escribe, menos la grafía vieja de MercadoPago."""
    for medio in ("efectivo", "transferencia", "tarjeta_debito",
                  "tarjeta_credito", "cuenta_corriente"):
        assert medios_pago.es_elegible(medio), medio


def test_la_grafia_vieja_se_sigue_leyendo():
    """🔴 El trinquete de la migración pendiente. Hay ventas con `mercado_pago`;
    el día que se saque de `HISTORICOS` sin migrar los datos, los tickets y los
    reportes de esas ventas muestran la clave cruda."""
    assert medios_pago.label("mercado_pago") == "Mercado Pago"
    # Y agrupa con la canónica, así que un reporte no la parte en dos filas.
    assert medios_pago.canonico("mercado_pago") == "mercadopago"


# ── El cobro por QR ────────────────────────────────────────────────────────

def test_el_conjunto_de_qr_acepta_las_dos_grafias():
    """Reconocer una sola dejaría el botón sin aparecer, o el pago sin sellar,
    según cuál."""
    assert "mercado_pago" in sales.MEDIOS_QR
    assert "mercadopago" in sales.MEDIOS_QR


def test_el_conjunto_de_qr_ahora_incluye_los_otros_electronicos():
    """🔴 **Esto arregla un defecto vivo.** El `frozenset` escrito a mano tenía
    sólo las dos grafías de MercadoPago, así que una venta cobrada por **Cuenta
    DNI o por otra billetera no sellaba la referencia del pago**: se acreditaba
    en MercadoPago sin quedar atada a la venta."""
    for medio in ("billetera", "cuenta_dni", "qr"):
        assert medio in sales.MEDIOS_QR, medio


def test_el_efectivo_NO_es_un_medio_de_qr():
    """El control: si el conjunto incluyera todo, el botón de cobrar con QR
    aparecería en una venta en efectivo."""
    assert "efectivo" not in sales.MEDIOS_QR
    assert "transferencia" not in sales.MEDIOS_QR
    assert "cuenta_corriente" not in sales.MEDIOS_QR


# ── El ticket ──────────────────────────────────────────────────────────────

def test_el_ticket_nombra_los_medios_propios_del_pos():
    """El mapa local se fue: la razón por la que existía —que LibraCore no
    conocía las tarjetas— dejó de valer cuando entraron a la lista canónica."""
    assert medios_pago.label("tarjeta_debito") == "Tarjeta de débito"
    assert medios_pago.label("tarjeta_credito") == "Tarjeta de crédito"
    assert medios_pago.label("cuenta_corriente") == "Cuenta corriente"


def test_el_ticket_de_una_venta_vieja_tambien(monkeypatch):
    """🔴 Un ticket **reimpreso** de una venta con `mercado_pago` tiene que salir
    bien. El mapa local la tenía; si la canónica no la tuviera, la reimpresión
    mostraría la clave cruda en el papel."""
    assert medios_pago.label("mercado_pago") == "Mercado Pago"
    # Y el módulo del ticket ya no declara ninguna: se verifica sobre el fuente,
    # porque un mapa privado no se puede consultar desde afuera.
    import inspect
    fuente = inspect.getsource(tickets)
    assert "_MEDIOS = {" not in fuente
    # El control: el fuente se leyó de verdad.
    assert "def ticket_de_venta" in fuente
