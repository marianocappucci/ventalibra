"""Los medios de pago que ofrecen los selectores del frontend.

🔴 Hasta el 2026-09-11 este producto tenía **tres listas propias** en el
frontend —POS, devolución y cobranza de cuenta corriente— y el backend no
validaba el medio: la lista del selector era lo único que decía qué se podía
cobrar. Ninguna de las tres ofrecía Cuenta DNI, otras billeteras ni cheque, que
el resto de la familia sí.

La lista sale de `libracore.medios_pago`, la misma que valida los payloads (ver
`routers/sales.py` y `routers/accounts.py`). La ruta es la de
`build_cajas_router` de LibraCore, que es la que pide
`libra-ui/comercio/medios-pago`: este producto no monta ese router entero
porque sus cajas no se administran desde acá, así que expone sólo esta lectura.
"""
from fastapi import APIRouter
from libracore import medios_pago

router = APIRouter(prefix="/api/cajas", tags=["medios"])


@router.get("/medios-disponibles")
def medios_disponibles() -> list[dict]:
    """`[{id, label}]`, en el orden de la pantalla. Incluye la cuenta
    corriente: la pantalla que cobra una deuda la filtra, porque fiar no es
    cobrar."""
    return medios_pago.para_selector()
