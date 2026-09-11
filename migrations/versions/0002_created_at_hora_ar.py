"""`sale_mp_orders.created_at` pasa a la hora de Argentina de la familia.

La mitad de VentaLibra del arreglo que [[libracore]] hizo en su revisión `0003`
y Restolibra en su `0002` (ver los docstrings de aquéllas para el diagnóstico
completo). Es la única columna con reloj del DDL propio de este producto.

**La diferencia con Restolibra.** Allá el DEFAULT era `datetime('now')`, que
estampaba UTC. Acá era `CURRENT_TIMESTAMP`, que en PostgreSQL ya salía en hora
de Argentina —es la zona de la sesión, y los servidores están en esa zona desde
el 2026-08-24—, pero:

- con **otro formato de texto** (`2026-09-11 18:30:00.123456-03`) que el del
  resto de las columnas de la familia (`2026-09-11 18:30:00`), que se comparan
  lexicográficamente y se parsean con `strptime`; y
- **dependiendo de la sesión**: un servidor sin `-c timezone` la devolvía en
  UTC sin que nada fallara.

Hoy nadie lee la columna (medido el 2026-09-11: sólo aparece en el DDL). Se
arregla porque la guarda de la familia la marcaba
(`tests/test_defaults_en_hora_de_argentina.py`, que llegó a este producto ese
día) y para que el primero que la lea no herede un formato distinto. Decisión
del humano del 2026-09-11: guarda + revisión, como Restolibra.

**Por qué es una revisión y no sólo la línea de `init_mp_qr_schema()`:** esa
función usa `CREATE TABLE IF NOT EXISTS`, así que sobre una base que ya existe
no cambia ningún DEFAULT. La función igual se corrigió, porque es la que define
cómo nace la tabla en un alta; esta revisión lleva el cambio a las existentes.

⚠️ **No toca las filas ya escritas.** Quedan con el formato viejo.
"""
from alembic import op

revision = "0002_created_at_hora_ar"
down_revision = "0001_baseline_ventalibra"
branch_labels = None
depends_on = None


#: La única columna con reloj de `init_schema_propio()`.
_COLUMNAS = (("sale_mp_orders", "created_at"),)

#: El DEFAULT que tenía antes, para el `downgrade()`.
_ANTES = "CURRENT_TIMESTAMP"


def _aplicar(expresion: str) -> None:
    """La traducción exacta a PostgreSQL —y saltear las columnas que no son
    TEXT— la hace `libracore.db.schema.alters_para_hora_ar()`, la misma función
    que usan la revisión del motor y las de los otros productos."""
    from libracore.db.schema import alters_para_hora_ar

    for sentencia in alters_para_hora_ar(op.get_bind(), _COLUMNAS, expresion):
        op.execute(sentencia)


def upgrade() -> None:
    from libracore.db.schema import AHORA_AR

    _aplicar(AHORA_AR)


def downgrade() -> None:
    _aplicar(_ANTES)
