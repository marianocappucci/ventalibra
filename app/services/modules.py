"""Lectura de modulos gateables por plan -- sqlite3 crudo sobre la tabla
`modulos` (ver app/db.py::init_modules_schema). Modulos que nunca se
sembraron (fuera de `plans.TODOS_LOS_MODULOS`) nunca se gatean -- mismo
criterio que ModuleRepository.is_enabled() de gestiolibra/medlibra.
"""
import sqlite3

from plans import TODOS_LOS_MODULOS


class ModuleRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def is_enabled(self, modulo: str) -> bool:
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
