"""Lectura de modulos gateables por plan -- sqlite3 crudo sobre la tabla
`modulos` (ver app/db.py::init_modules_schema). Modulos que nunca se
sembraron (fuera de `plans.TODOS_LOS_MODULOS`) nunca se gatean -- mismo
criterio que ModuleRepository.is_enabled() de gestiolibra/medlibra.

🔴 **Salvo los add-ons (`plans.ADDONS`), que van al reves.** Un add-on tambien
queda afuera de `TODOS_LOS_MODULOS` -- no es de ningun plan y no se siembra --,
asi que con la regla de arriba `require_module("<add-on>")` daria siempre
`True` y el add-on quedaria prendido en todas las instancias sin que nadie lo
haya encendido. Para un add-on la ausencia de fila significa APAGADO: se
habilita solo cuando el backoffice escribio una fila con `habilitado`
verdadero (`app.database.set_addon`).
"""

from libracore.db.core import Conexion

from plans import ADDONS, TODOS_LOS_MODULOS


class ModuleRepository:
    def __init__(self, conn: Conexion):
        self._conn = conn

    def is_enabled(self, modulo: str) -> bool:
        if modulo in ADDONS:
            # Add-on: apagado mientras no haya una fila que diga lo contrario.
            # Ver el docstring del modulo.
            row = self._conn.execute(
                "SELECT habilitado FROM modulos WHERE modulo = ?", (modulo,)
            ).fetchone()
            return row is not None and bool(row[0])
        if modulo not in TODOS_LOS_MODULOS:
            return True
        row = self._conn.execute(
            "SELECT habilitado FROM modulos WHERE modulo = ?", (modulo,)
        ).fetchone()
        return bool(row[0]) if row is not None else True

    def get_all(self) -> dict[str, bool]:
        rows = self._conn.execute("SELECT modulo, habilitado FROM modulos").fetchall()
        return {row[0]: bool(row[1]) for row in rows}

    def set_enabled(self, modulo: str, enabled: bool) -> None:
        """Setter directo, para tests y para el backoffice de planes --
        `plans.aplicar_plan_en_db` es la via real de produccion (aplica un
        plan completo contra el archivo, sin conexion viva), esto es para
        tocar un solo modulo contra una conexion ya abierta."""
        self._conn.execute(
            "UPDATE modulos SET habilitado = ? WHERE modulo = ?", (int(enabled), modulo)
        )
        self._conn.commit()
