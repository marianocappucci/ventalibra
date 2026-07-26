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


def modulos_de_plan(plan: str) -> set[str]:
    return set(PLAN_MODULOS.get(plan, set()))


def aplicar_plan_en_db(db_path: str, plan: str) -> None:
    """Escribe el estado de modulos directo en la DB sqlite de un cliente
    -- idempotente (INSERT OR IGNORE + UPDATE), mismo patron que
    gestiolibra/medlibra."""
    import sqlite3

    activos = modulos_de_plan(plan)
    con = sqlite3.connect(db_path)
    try:
        for modulo in sorted(TODOS_LOS_MODULOS):
            habilitado = 1 if modulo in activos else 0
            con.execute(
                "INSERT OR IGNORE INTO modulos (modulo, habilitado, plan) VALUES (?, ?, ?)",
                (modulo, habilitado, plan),
            )
            con.execute(
                "UPDATE modulos SET habilitado = ?, plan = ? WHERE modulo = ?",
                (habilitado, plan, modulo),
            )
        con.commit()
    finally:
        con.close()
