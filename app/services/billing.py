"""Facturacion/caja para TiendaLibra, compuesto sobre libracore.db.

libracore.db es sqlite3 crudo, sin capa de abstraccion -- una conexion
propia, separada de la base principal de LibraCommerce/users/sequences
(ver DECISIONS.md ADR-007). TiendaLibra es de instancia unica por cliente
(arquitectura silo), asi que hay una sola "empresa" ARCA -- una constante
fija, no una tabla de empresas. Mismo patron que
medlibra/app/services/billing.py y gestiolibra/app/services/billing.py.

A diferencia de esos dos productos (donde caja solo se toca si hay
factura, seña+saldo de un turno), en retail toda venta cobrada debe
quedar en caja sin importar si se factura o no -- decision explicita del
usuario, 2026-07-25. Por eso `record_sale_payment` es una funcion aparte
de `invoice_sale`, llamada siempre al confirmar una venta; `invoice_sale`
solo se llama si el operador pidio factura para esa venta puntual.
"""
import os
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from libracore import arca_facturacion
from libracore.db import arca_config as db_arca_config
from libracore.db import caja as db_caja
from libracore.db import core as libracore_core
from libracore.db import facturas as db_facturas
from libracore.db.schema import init_core_schema

EMPRESA = "tienda"

TIPO_FACTURA_A = 1
TIPO_FACTURA_B = 6

# Mismo mapeo que medlibra/gestiolibra (a su vez tomado de
# web/routers/facturas.py de Contalibra) -- dict chico y estable, no
# migrado a libracore por no tener logica propia.
IVA_CODES = {
    "Responsable Inscripto": 1,
    "IVA Responsable Inscripto": 1,
    "Monotributista": 6,
    "Responsable Monotributo": 6,
    "IVA Exento": 4,
    "Consumidor Final": 5,
    "No Alcanzado": 3,
    "IVA No Responsable": 3,
}

_IVA_RATE = Decimal("0.21")


def configure(db_path: str) -> None:
    """Llamar una vez al arrancar la app: configura libracore.db contra su
    propio archivo SQLite (independiente de la base principal) y asegura
    que el schema compartido y una caja por defecto existan."""
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    libracore_core.configure(db_path)
    conn = libracore_core.get_connection()
    try:
        init_core_schema(conn)
        conn.commit()
    finally:
        conn.close()
    if db_caja.get_default_caja_id() is None:
        caja_id = db_caja.create_caja_config(
            "Caja TiendaLibra", "", list(db_caja.MEDIOS_PAGO_LABELS),
        )
        db_caja.set_default_caja(caja_id)


def get_arca_config() -> dict | None:
    return db_arca_config.obtener_arca_config(EMPRESA)


def set_arca_config(
    cuit: str, punto_venta: int, clave_path: str, certificado_path: str,
    ambiente: str = "homologacion",
) -> dict:
    if get_arca_config() is None:
        db_arca_config.crear_arca_config(
            EMPRESA, cuit, punto_venta, clave_path, certificado_path, ambiente,
        )
    else:
        db_arca_config.actualizar_arca_config(
            EMPRESA, cuit=cuit, punto_venta=punto_venta,
            clave_path=clave_path, certificado_path=certificado_path, ambiente=ambiente,
        )
    return get_arca_config()


def _tipo_comprobante(condicion_iva: str | None) -> int:
    return TIPO_FACTURA_A if condicion_iva == "Responsable Inscripto" else TIPO_FACTURA_B


def _split_iva(total: Decimal) -> tuple[Decimal, Decimal]:
    """Asume `total` como monto final (IVA incluido) y separa subtotal/IVA
    al 21% -- misma simplificacion documentada que medlibra/gestiolibra: no
    contempla otras alicuotas ni exentos; a revisar con un contador antes
    de facturar contra ARCA real."""
    subtotal = (total / (Decimal("1") + _IVA_RATE)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    iva_amount = total - subtotal
    return subtotal, iva_amount


async def invoice_sale(customer_billing: dict | None, sale, referencia: str) -> dict:
    """Emite una factura por el total de la venta -- un solo comprobante,
    sin sena/saldo (a diferencia de invoice_appointment de medlibra/
    gestiolibra): en un POS de retail la venta se cobra entera al
    confirmar. No genera movimiento de caja -- eso es record_sale_payment,
    llamado siempre, factures o no.
    """
    total = Decimal(str(sale.total))
    arca_cfg = get_arca_config()
    punto_venta = arca_cfg["punto_venta"] if arca_cfg else 1
    condicion_iva = customer_billing.get("condicion_iva") if customer_billing else None
    cuit = customer_billing.get("cuit") if customer_billing else None
    razon = customer_billing.get("display_name") if customer_billing else "Consumidor Final"
    tipo = _tipo_comprobante(condicion_iva)
    subtotal, iva_amount = _split_iva(total)

    numero, ta, arca_used = await arca_facturacion.get_next_numero_with_arca(punto_venta, tipo)
    factura_id = db_facturas.create_factura(
        tipo, punto_venta, numero, date.today().isoformat(),
        cuit or "", razon or "",
        IVA_CODES.get(condicion_iva, IVA_CODES["Consumidor Final"]),
        [], float(subtotal), float(iva_amount), float(total),
    )
    factura = db_facturas.get_factura(factura_id)
    return await arca_facturacion.solicitar_cae(factura_id, factura, ta, arca_used)


def record_sale_payment(sale, medio_pago: str, referencia: str, factura_id: int | None = None) -> None:
    """Movimiento de caja para una venta confirmada -- siempre, factures o
    no. `create_caja_movimiento` es idempotente por (referencia,
    factura_id), asi que reintentar con la misma referencia no duplica."""
    db_caja.create_caja_movimiento(
        date.today().isoformat(), "ingreso", f"Venta {sale.number}",
        Decimal(str(sale.total)), referencia=referencia, factura_id=factura_id, medio_pago=medio_pago,
    )
