"""Preferencias del comercio. Por ahora, la balanza de mostrador."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from libracommerce.domain.scale import ScaleFormat, ScaleValueKind

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


def _to_dict(fmt: ScaleFormat) -> dict:
    return {
        "prefix": fmt.prefix,
        "code_digits": fmt.code_digits,
        "value_digits": fmt.value_digits,
        "value_kind": fmt.value_kind.value,
        "divisor": fmt.divisor,
        "total_digits": fmt.total_digits,
    }
