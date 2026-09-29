"""Planes y modulos gateables de VentaLibra -- mismo patron exacto que
plans.py de gestiolibra/medlibra (PLANES/PLAN_MODULOS/aplicar_plan_en_db),
consumido por libracore.provisioning via import diferido.

Dos planes, y lo que los separa es lo **fiscal y lo multisucursal**, no un
tablero (ADR-048, decision del humano 2026-09-29):

- **Basico**: un solo local (UNA sucursal, con los depositos que necesite).
  Todo lo demas -- POS, stock, compras, caja, clientes y proveedores, cuenta
  corriente, promociones, margen, dashboard, etiquetas, tesoreria, egresos y
  libros IVA -- esta libre.
- **Premium**: suma `facturacion` (ARCA) y `multisucursal` (mas de una
  sucursal y la transferencia de mercaderia entre sucursales).

Catalogo, inventario, ventas, compras, tesoreria, egresos y libros IVA son
siempre libres en todos los planes (equivalente a "turnos" en Gestiolibra /
todo el dominio clinico en MedLibra) -- lo mismo que caja, que en VentaLibra
es "siempre" por decision de negocio (ver DECISIONS.md ADR-007, independiente
del tema fiscal). `dashboard` dejo de ser un modulo gateable: ya no distingue
un plan (ADR-048, que reemplaza a ADR-039 en ese punto).

## Lo que ya no existe, y que pasa con las instancias que lo tienen guardado

El estado de una instancia vive en la tabla `modulos` (`modulo`, `habilitado`,
`plan`), y el gate lee **solo `habilitado`** (`ModuleRepository.is_enabled`).

- **Plan retirado (`estandar`)**: ver `PLANES_RETIRADOS`. Se lo trata como
  `premium` -- tenia facturacion y, hasta ADR-048, las sucursales eran libres --,
  **a la vista**: `modulos_de_plan`, `aplicar_plan_en_db` y el arranque de la
  app (`app.db.init_modules_schema`) lo registran con un `WARNING`, y
  `aplicar_plan_en_db` reescribe la etiqueta a `premium`. Un plan que no es de
  ninguna de las dos listas **no** se aplica: `aplicar_plan_en_db` levanta
  `ValueError` en vez de apagar todos los modulos de la instancia por un typo.
- **Modulo retirado (`dashboard`)**: ver `MODULOS_RETIRADOS`. La fila que quede
  en `modulos` no se borra ni se lee: `is_enabled` da `True` para todo modulo
  fuera de `TODOS_LOS_MODULOS`, asi que aunque diga `habilitado=0` (lo tenian
  asi los planes Basico y Estandar) no corta nada.
"""
import logging

logger = logging.getLogger(__name__)

PLANES = ["basico", "premium"]
PLAN_LABELS = {"basico": "Básico", "premium": "Premium"}
PLAN_PRECIOS = {"basico": 20000, "premium": 55000}

_BASICO: set[str] = set()
_PREMIUM = _BASICO | {"facturacion", "multisucursal"}
PLAN_MODULOS = {"basico": set(_BASICO), "premium": set(_PREMIUM)}

TODOS_LOS_MODULOS = set(PLAN_MODULOS["premium"]) | _BASICO

# Planes que existieron y ya no se venden, con el plan que los reemplaza. Hoy se
# reduce a `estandar` (ADR-009, tres planes; ADR-048 lo retira): tenia
# `facturacion`, asi que el reemplazo es `premium` -- el unico plan con
# facturacion --, y la instancia no pierde nada de lo que ya usaba. La unica que
# lo tenia guardado al 2026-09-29 era `demo`.
PLANES_RETIRADOS = {"estandar": "premium"}

# Modulos que existieron como gateables y ya no lo son. Quedan listados para
# que quien lea una fila vieja de `modulos` sepa que no es un olvido.
MODULOS_RETIRADOS = {"dashboard"}

# Add-ons: modulos sueltos que NO pertenecen a ningun plan. Estan disponibles en
# cualquier plan, vienen APAGADOS y se prenden por instancia desde el backoffice
# (`libracore.admin.services.set_addon`, que valida contra este set y escribe
# por `app.database.set_addon` dentro del contenedor). Mismo criterio que
# `mayorista` en Contalibra o `modo_simple` en LibraDesk.
#
# 🔴 Por eso quedan AFUERA de los planes y de `TODOS_LOS_MODULOS`: si entraran,
# `init_modules_schema` los sembraria prendidos en cada arranque y
# `aplicar_plan_en_db` los prenderia o apagaria solo con cambiar de plan -- un
# adicional que se activa o se desactiva en silencio.
#
# - `resguardo_externo`: el enlace de la copia externa con la nube del cliente
#   (`libracore.resguardo_enlace`, montado en `app/main.py`).
ADDONS = {"resguardo_externo"}


def plan_vigente(plan: str) -> str:
    """El plan con el que se opera hoy: el mismo, o el que reemplaza a uno retirado.

    Un plan retirado (`PLANES_RETIRADOS`) se resuelve **avisando**, no en
    silencio: cada vez que alguien pregunta por `estandar` queda un `WARNING`
    en el log. Un plan desconocido vuelve igual (no es un plan retirado y no
    hay a que mapearlo); quien lo aplica decide que hacer.
    """
    reemplazo = PLANES_RETIRADOS.get(plan)
    if reemplazo is None:
        return plan
    logger.warning(
        "El plan %r ya no se vende (ADR-048): se lo trata como %r. "
        "Reaplicalo con plans.aplicar_plan_en_db(<db>, %r) para actualizar la etiqueta guardada.",
        plan, reemplazo, reemplazo,
    )
    return reemplazo


def modulos_de_plan(plan: str) -> set[str]:
    return set(PLAN_MODULOS.get(plan_vigente(plan), set()))


def aplicar_plan_en_db(db_path: str, plan: str) -> None:
    """Escribe el estado de modulos directo en la DB sqlite de un cliente.

    Shim sobre libracore.provisioning.apply_plan_modules (extraído
    2026-07-26: el cuerpo era idéntico en Gestiolibra/MedLibra/VentaLibra
    salvo el nombre de la variable, ver
    wiki/analyses/auditoria-duplicacion-familia-libra.md).

    Los add-ons se restan de `all_modules` a proposito: aplicar un plan no
    tiene que tocarlos (ver `ADDONS`). Hoy ya estan afuera de
    `TODOS_LOS_MODULOS`, pero la resta deja la regla escrita aca, donde se
    aplica, y no depende de que nadie los sume al set por error.

    Un plan retirado se aplica como su reemplazo y **con la etiqueta del
    reemplazo** (`estandar` -> `premium`), avisando (ver `plan_vigente`). Un
    plan desconocido levanta `ValueError`: sin esto `modulos_de_plan` daria un
    set vacio y la instancia quedaria con TODO apagado, facturacion incluida,
    por un error de tipeo."""
    vigente = plan_vigente(plan)
    if vigente not in PLAN_MODULOS:
        raise ValueError(f"Plan desconocido: {plan!r}. Los vigentes son {PLANES}.")
    from libracore.provisioning import apply_plan_modules
    apply_plan_modules(
        db_path, active_modules=set(PLAN_MODULOS[vigente]),
        all_modules=TODOS_LOS_MODULOS - ADDONS, plan=vigente,
    )
