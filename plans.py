"""Planes y modulos gateables de VentaLibra -- mismo patron exacto que
plans.py de gestiolibra/medlibra (PLANES/PLAN_MODULOS/aplicar_plan_en_db),
consumido por libracore.provisioning via import diferido.

**Un unico plan, con todo incluido** (ADR-072, decision del humano 2026-10-09).
Se llama `unico` (etiqueta «Plan unico», $39.900 de lista por instancia, con UNA
sucursal incluida) y trae todas las funcionalidades: POS, stock, compras, caja,
clientes y proveedores, cuenta corriente, promociones, margen, dashboard,
etiquetas, tesoreria, egresos, libros IVA, `facturacion` (ARCA) y
`multisucursal` (mas de una sucursal y la transferencia de mercaderia entre
sucursales). Ya no existen los planes Basico ni Premium.

El precio por sucursal adicional ($19.950) es **comercial**: el sistema no lo
modela, no cuenta sucursales ni cobra por ellas. `multisucursal` sigue siendo un
modulo gateable (`TODOS_LOS_MODULOS`) y NO se vacia: la SPA arma la pantalla con
la lista `modulos` de `/auth/me` (`TODOS_LOS_MODULOS | ADDONS` filtrado por los
habilitados), asi que si el set quedara vacio la facturacion desapareceria de la
pantalla. El plan unico los prende a los dos; que un modulo este apagado en una
instancia es una decision administrativa (una instancia suspendida, un
add-on...), ya no una diferencia de plan.

Historia: ADR-009 fijo tres planes (Basico, Estandar, Premium) separados por
`facturacion`; ADR-048 (2026-09-29) los redujo a dos separados por lo fiscal y
lo multisucursal; ADR-072 los reduce a uno. Catalogo, inventario, ventas,
compras, tesoreria, egresos y libros IVA son siempre libres -- lo mismo que
caja, que en VentaLibra es "siempre" por decision de negocio (ver DECISIONS.md
ADR-007, independiente del tema fiscal). `dashboard` dejo de ser un modulo
gateable en ADR-048.

## Lo que ya no existe, y que pasa con las instancias que lo tienen guardado

El estado de una instancia vive en la tabla `modulos` (`modulo`, `habilitado`,
`plan`), y el gate lee **solo `habilitado`** (`ModuleRepository.is_enabled`).

- **Planes retirados (`basico`, `premium`, `estandar`)**: ver `PLANES_RETIRADOS`.
  Todos se resuelven como `unico`, **a la vista**: `modulos_de_plan`,
  `aplicar_plan_en_db` y el arranque de la app (`app.db.init_modules_schema`) lo
  registran con un `WARNING`. `aplicar_plan_en_db` los aplica como `unico`
  (todo prendido, etiqueta `unico`). **Y el arranque migra la instancia sola**:
  una instancia que quedo guardada como `basico` tiene `facturacion` y
  `multisucursal` APAGADAS; si el arranque solo avisara, quedaria asi para
  siempre sin que nadie reaplique nada. Por eso `init_modules_schema`
  **prende** los modulos del plan vigente y reescribe la etiqueta a `unico`.
  Solo prende, nunca apaga, y no toca los add-ons.
- Un plan que no es de ninguna de las dos listas **no** se aplica:
  `aplicar_plan_en_db` levanta `ValueError` en vez de apagar todos los modulos
  de la instancia por un typo.
- **Modulo retirado (`dashboard`)**: ver `MODULOS_RETIRADOS`. La fila que quede
  en `modulos` no se borra ni se lee: `is_enabled` da `True` para todo modulo
  fuera de `TODOS_LOS_MODULOS`, asi que aunque diga `habilitado=0` (lo tenian
  asi los planes Basico y Estandar) no corta nada.
"""
import logging

logger = logging.getLogger(__name__)

PLANES = ["unico"]
PLAN_LABELS = {"unico": "Plan único"}
# Precio de lista por instancia, con una sucursal incluida. La sucursal adicional
# ($19.950) es comercial y no se modela aca (ADR-072).
PLAN_PRECIOS = {"unico": 39900}

_UNICO = {"facturacion", "multisucursal"}
PLAN_MODULOS = {"unico": set(_UNICO)}

# 🔴 NO vaciar: la SPA arma la pantalla con `modulos` de `/auth/me`, que sale de
# esto (mas los add-ons) filtrado por los habilitados.
TODOS_LOS_MODULOS = set(_UNICO)

# Planes que existieron y ya no se venden, con el plan que los reemplaza. Hoy
# los tres se resuelven como `unico`: `estandar` (ADR-009; retirado en ADR-048),
# `basico` y `premium` (ADR-048; retirados en ADR-072). El reemplazo trae todo lo
# que cualquiera de ellos tenia, asi que la instancia no pierde nada. Solo
# `basico` tenia modulos apagados: ahi el arranque los PRENDE (ver
# `app.db.init_modules_schema`).
PLANES_RETIRADOS = {"estandar": "unico", "basico": "unico", "premium": "unico"}

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
    silencio: cada vez que alguien pregunta por `basico`, `premium` o `estandar`
    queda un `WARNING` en el log. Un plan desconocido vuelve igual (no es un
    plan retirado y no hay a que mapearlo); quien lo aplica decide que hacer.
    """
    reemplazo = PLANES_RETIRADOS.get(plan)
    if reemplazo is None:
        return plan
    logger.warning(
        "El plan %r ya no se vende (ADR-072): se lo trata como %r. "
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
    reemplazo** (`basico`/`premium`/`estandar` -> `unico`), avisando (ver
    `plan_vigente`); como el reemplazo trae todo, aplicar `basico` PRENDE los
    modulos que tenia apagados. Un
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
