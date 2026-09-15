"""El vocabulario de medios de pago en este producto.

🔴 **Este POS usa el vocabulario canónico, y ya no queda ninguna divergencia.**
`efectivo`, `transferencia`, `tarjeta_debito`, `tarjeta_credito`, `mercadopago`
y `cuenta_corriente` son exactamente las claves de la familia — de hecho
VentaLibra fue quien partió la tarjeta en dos, y por eso la lista canónica la
partió también.

Lo que divergía era `mercado_pago` con guión bajo, y **se cerró en ese orden**:
primero los datos (`app/normalizacion_medios.py`, ADR-024), después el selector,
y último la baja del histórico en el motor (`libracore v1.52.0`). Por eso los
tests de acá abajo afirman que la grafía vieja **ya no se conoce**: es la
propiedad que se quiere sostener, no una regresión.
"""
import inspect

from libracore import medios_pago

from app.services import tickets


def test_los_medios_del_pos_son_los_de_la_familia():
    """Los seis que este POS ofrece, todos elegibles en la lista canónica."""
    for medio in ("efectivo", "transferencia", "tarjeta_debito",
                  "tarjeta_credito", "mercadopago", "cuenta_corriente"):
        assert medios_pago.es_elegible(medio), medio


def test_el_motor_pineado_ya_no_conoce_la_grafia_vieja():
    """🔴 Afirma el COMPORTAMIENTO del motor instalado, no el string del pin.

    Un test que leyera `pyproject.toml` buscando `v1.52.0` pasaría igual con un
    wheel viejo instalado encima. Esto ejercita el módulo que la app importa de
    verdad, así que un pin rebajado por debajo de v1.52.0 lo pone rojo.

    Y que la devuelva **cruda** es lo que se quiere: con los datos migrados, ver
    `mercado_pago` escrito en un ticket o en un reporte es la señal de que algo
    la volvió a escribir. Una etiqueta linda escondería justamente esa señal.
    """
    assert medios_pago.label("mercado_pago") == "mercado_pago"
    assert not medios_pago.es_elegible("mercado_pago")
    assert "mercado_pago" not in medios_pago.MEDIOS_ELECTRONICOS
    # El control: la grafía buena sí está, en las tres. Sin esto, un módulo
    # vacío —o un import que fallara silenciosamente— pasaría todo lo de arriba.
    assert medios_pago.label("mercadopago") == "Mercado Pago"
    assert medios_pago.es_elegible("mercadopago")
    assert "mercadopago" in medios_pago.MEDIOS_ELECTRONICOS


def test_las_historicas_que_SI_siguen_vivas_se_leen():
    """El trinquete del motor sigue en pie para las otras cinco.

    `mercado_pago` salió porque se migraron sus filas; las demás tienen filas
    vivas en bases reales de otros productos y **no se sacan**. Si alguna
    desapareciera, un cierre de caja mostraría un bucket con el slug crudo.
    """
    for medio in ("tarjeta", "debito", "credito", "cuenta corriente"):
        assert medios_pago.label(medio) not in ("", medio), medio


# ── El cobro por QR ────────────────────────────────────────────────────────
#
# 🔴 **Los tres tests de `sales.MEDIOS_QR` se retiran (2026-09-14, F3,
# DECISIONS.md ADR-025), no se portan.** `app/routers/sales.py` ya no declara
# ese `frozenset` -- se fue con `confirm_sale` y el resto de las escrituras
# retiradas (410): era el conjunto que decidía, en el POS legado, si un pago
# se cobraba escaneando el QR. Medido (`grep -rn MEDIOS_QR app/`): no queda
# ninguna referencia en el código del producto.
#
# El invariante que probaban -- qué medios cobran por QR -- no desapareció,
# **se angostó y se movió al motor**: `libracommerce.web.ventas_router.
# PagoPayload` valida `cobrar_con_qr` con `_el_qr_es_de_mercadopago`, y esa
# validación es **más estricta** que el `frozenset` de acá (D2, "el modelo de
# la familia"): sólo el medio `mercadopago` puede pedir `cobrar_con_qr=True`,
# no toda `medios_pago.MEDIOS_ELECTRONICOS` (billetera, cuenta_dni, qr
# quedan afuera). No es un recorte accidental de esta migración: es una
# decisión del motor compartido por Contalibra y Restolibra, y ese es el
# repo que la prueba -- repetirla acá mediría código que ya no es de
# VentaLibra. Ver `PagoPayload._el_qr_es_de_mercadopago` en
# `libracommerce.web.ventas_router` (instalado en `.venv`) para el detalle.


# ── El ticket ──────────────────────────────────────────────────────────────

def test_el_ticket_nombra_los_medios_propios_del_pos():
    """El mapa local se fue: la razón por la que existía —que LibraCore no
    conocía las tarjetas— dejó de valer cuando entraron a la lista canónica."""
    assert medios_pago.label("tarjeta_debito") == "Tarjeta de débito"
    assert medios_pago.label("tarjeta_credito") == "Tarjeta de crédito"
    assert medios_pago.label("cuenta_corriente") == "Cuenta corriente"
    assert medios_pago.label("mercadopago") == "Mercado Pago"


def test_el_modulo_del_ticket_ya_no_declara_ningun_mapa_propio():
    """Se verifica sobre el fuente porque un mapa privado no se puede consultar
    desde afuera."""
    fuente = inspect.getsource(tickets)
    assert "_MEDIOS = {" not in fuente
    # El control: el fuente se leyó de verdad. Sin esto, un `getsource` que
    # devolviera vacío pasaría el assert de arriba.
    assert "def ticket_de_venta" in fuente
