"""Planes y modulos gateables de VentaLibra -- mismo patron exacto que
plans.py de gestiolibra/medlibra (PLANES/PLAN_MODULOS/aplicar_plan_en_db),
consumido por libracore.provisioning via import diferido.

Catalogo, inventario, ventas y compras son siempre libres en todos los
planes (equivalente a "turnos" en Gestiolibra / todo el dominio clinico en
MedLibra) -- lo mismo que caja, que en VentaLibra es "siempre" por decision
de negocio (ver DECISIONS.md ADR-007, independiente del tema fiscal).
Facturacion es el unico modulo gateable por ahora; Premium queda con
margen para dashboard/reportes cuando se construyan (Fase 5 del
ROADMAP.md).
"""
PLANES = ["basico", "estandar", "premium"]
PLAN_LABELS = {"basico": "Básico", "estandar": "Estándar", "premium": "Premium"}
PLAN_PRECIOS = {"basico": 20000, "estandar": 35000, "premium": 55000}

_BASICO: set[str] = set()
_ESTANDAR = _BASICO | {"facturacion"}
_PREMIUM = _ESTANDAR | set()  # dashboard/reportes se suman aca cuando existan
PLAN_MODULOS = {"basico": set(_BASICO), "estandar": set(_ESTANDAR), "premium": set(_PREMIUM)}

TODOS_LOS_MODULOS = set(PLAN_MODULOS["premium"]) | _ESTANDAR | _BASICO

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


def modulos_de_plan(plan: str) -> set[str]:
    return set(PLAN_MODULOS.get(plan, set()))


def aplicar_plan_en_db(db_path: str, plan: str) -> None:
    """Escribe el estado de modulos directo en la DB sqlite de un cliente.

    Shim sobre libracore.provisioning.apply_plan_modules (extraído
    2026-07-26: el cuerpo era idéntico en Gestiolibra/MedLibra/VentaLibra
    salvo el nombre de la variable, ver
    wiki/analyses/auditoria-duplicacion-familia-libra.md).

    Los add-ons se restan de `all_modules` a proposito: aplicar un plan no
    tiene que tocarlos (ver `ADDONS`). Hoy ya estan afuera de
    `TODOS_LOS_MODULOS`, pero la resta deja la regla escrita aca, donde se
    aplica, y no depende de que nadie los sume al set por error."""
    from libracore.provisioning import apply_plan_modules
    apply_plan_modules(
        db_path, active_modules=modulos_de_plan(plan),
        all_modules=TODOS_LOS_MODULOS - ADDONS, plan=plan,
    )
