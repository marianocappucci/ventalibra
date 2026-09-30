"""La baja de un lote (`POST /api/vencimientos/merma`) está DESHABILITADA hasta A-4 (ADR-052).

🔴 **Por qué.** Mientras las ventas (y las devoluciones, los ajustes y las transferencias) descuenten del stock «sin lote», el saldo de un
lote sobreestima lo que hay en cuanto ocurre CUALQUIER salida posterior a su entrada o asignación, y el motor no puede probar de qué
bucket salió físicamente la mercadería: mermar ese lote descontaría dos veces unidades ya vendidas. La guarda del motor (v0.29.1: mira el
stock total y las salidas sin conciliar) es de mejor esfuerzo, no una garantía (ADR-018 del motor, nota del 2026-09-30). Decisión
(2026-09-30): hasta que las ventas descuenten por lote (A-4, FEFO) VentaLibra no expone la baja de un lote. La asignación de vencimiento
(que conserva el total) y el reporte sí.

**Cómo.** El router de escritura del motor aplica `dependencias_movimientos` a `asignar` y a `merma` juntas y no admite una por operación,
así que es una dependencia del producto que mira el método y la ruta y deja pasar todo lo demás. **Corre DESPUÉS de la guarda de
permisos** (`requiere("vencimientos.mover")`, primera de la lista): un anónimo sigue recibiendo 401 y quien no tiene la capacidad, 403;
el resto, incluido el admin, recibe 409 sin tocar el motor.

**Cómo reactivarla (al llegar A-4):** quitar `merma_deshabilitada` de `dependencias_movimientos` en `app/main.py` y retirar el marcador
`MERMA_DESHABILITADA` de `tests/test_vencimientos.py` (los tests que lo usan vuelven a afirmar que la merma funciona).
"""
from fastapi import HTTPException, Request

RUTA_DE_LA_MERMA = "/api/vencimientos/merma"

MENSAJE = (
    "La baja de un lote se habilita cuando las ventas descuenten por lote (etapa siguiente de vencimientos): hoy el saldo de un lote "
    "puede incluir unidades ya vendidas y mermarlo las descontaría dos veces. Para dar de baja mercadería vencida usá el ajuste de stock."
)


def _es_la_merma(request: Request) -> bool:
    """¿La petición va al endpoint de la merma? Se mira la RUTA RESUELTA por el router (`scope["route"]`) **y** la URL pedida:
    bajo un `root_path` (un prefijo ASGI de un proxy) Starlette lo descarta para elegir el endpoint, pero `request.url.path` lo
    conserva, y comparar sólo la URL dejaba pasar `POST /<prefijo>/api/vencimientos/merma` (hallazgo de Codex, 2026-09-30)."""
    ruta_resuelta = str(getattr(request.scope.get("route"), "path", "") or "").rstrip("/")
    url = request.url.path.rstrip("/")
    return ruta_resuelta == RUTA_DE_LA_MERMA or url == RUTA_DE_LA_MERMA or url.endswith(RUTA_DE_LA_MERMA)


def merma_deshabilitada(request: Request) -> None:
    """409 con `MENSAJE` para `POST /api/vencimientos/merma`; no hace nada en ninguna otra ruta."""
    if request.method == "POST" and _es_la_merma(request):
        raise HTTPException(409, MENSAJE)
