"""Preferencias del comercio: la balanza de mostrador y el ticket impreso.

Las dos son configuración de hardware — qué balanza usa el local, qué ancho
de papel tiene la ticketeadora — que no se puede adivinar desde el código y
que el dueño tiene que poder ajustar sin un redeploy.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from libracommerce.domain.scale import ScaleFormat, ScaleValueKind
from libracore import config_manager

from ..services.scale import ScaleService

router = APIRouter(prefix="/settings", tags=["settings"])


class ScaleFormatIn(BaseModel):
    prefix: str = "20"
    code_digits: int = 5
    value_digits: int = 5
    value_kind: str = "weight"
    divisor: int = 1000
    total_digits: int = 13


class ScaleFormatOut(ScaleFormatIn):
    pass


def _service(request: Request) -> ScaleService:
    return ScaleService(request.app.state.conn)


@router.get("/scale", response_model=ScaleFormatOut | None)
def get_scale(request: Request):
    """La configuracion vigente, o null si el local no usa balanza."""
    fmt = _service(request).get_format()
    return None if fmt is None else ScaleFormatOut(**_to_dict(fmt))


@router.put("/scale", response_model=ScaleFormatOut)
def set_scale(data: ScaleFormatIn, request: Request):
    try:
        fmt = ScaleFormat(
            prefix=data.prefix,
            code_digits=data.code_digits,
            value_digits=data.value_digits,
            value_kind=ScaleValueKind(data.value_kind),
            divisor=data.divisor,
            total_digits=data.total_digits,
        )
    except ValueError as exc:
        # Un formato incoherente se rechaza al guardarlo: si entrara, cada
        # etiqueta de la balanza se leeria mal hasta que alguien lo note.
        raise HTTPException(422, str(exc))
    _service(request).set_format(fmt)
    return ScaleFormatOut(**_to_dict(fmt))


@router.delete("/scale", status_code=204)
def clear_scale(request: Request):
    """Apaga la balanza: los codigos vuelven a leerse todos como comunes."""
    _service(request).set_format(None)


class TicketConfigIn(BaseModel):
    #: 58 u 80. Son los dos formatos de rollo del mercado.
    ancho_mm: str = "80"
    fuente_size: int = 9
    mostrar_logo: bool = False
    linea_corte: bool = True
    pie: str = ""


class TicketConfigOut(TicketConfigIn):
    pass


@router.get("/ticket", response_model=TicketConfigOut)
def get_ticket(request: Request):
    cfg = config_manager.load()
    return TicketConfigOut(
        ancho_mm=str(cfg.get("ticket_ancho_mm", "80")),
        fuente_size=int(cfg.get("ticket_fuente_size", "9") or 9),
        mostrar_logo=str(cfg.get("ticket_mostrar_logo", "0")) == "1",
        linea_corte=str(cfg.get("ticket_linea_corte", "1")) == "1",
        pie=str(cfg.get("ticket_pie", "")),
    )


@router.put("/ticket", response_model=TicketConfigOut)
def set_ticket(data: TicketConfigIn, request: Request):
    if data.ancho_mm not in ("58", "80"):
        # Un ancho que la ticketeadora no tiene sale cortado o con media hoja
        # en blanco, y sólo se nota con el rollo puesto.
        raise HTTPException(422, "el ancho de papel tiene que ser 58 u 80 mm")
    if not 6 <= data.fuente_size <= 14:
        raise HTTPException(422, "el tamaño de fuente tiene que estar entre 6 y 14")
    cfg = config_manager.load()
    cfg.update({
        "ticket_ancho_mm": data.ancho_mm,
        "ticket_fuente_size": str(data.fuente_size),
        "ticket_mostrar_logo": "1" if data.mostrar_logo else "0",
        "ticket_linea_corte": "1" if data.linea_corte else "0",
        "ticket_pie": data.pie,
    })
    config_manager.save(cfg)
    return get_ticket(request)


def _to_dict(fmt: ScaleFormat) -> dict:
    return {
        "prefix": fmt.prefix,
        "code_digits": fmt.code_digits,
        "value_digits": fmt.value_digits,
        "value_kind": fmt.value_kind.value,
        "divisor": fmt.divisor,
        "total_digits": fmt.total_digits,
    }
