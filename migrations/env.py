"""Entorno de Alembic para las tablas **propias** de VentaLibra.

De las 63 tablas de una instancia, esta cadena maneja **5**: `users`,
`sequences`, `party_billing`, `party_roles` y `sale_mp_orders`. Las otras son de
los motores y cada uno las mantiene por su cuenta — ver `app/schema_propio.py`,
que tiene el reparto completo y el caso aparte de `modulos`.

Tres decisiones, y las tres tienen el mismo motivo de fondo (que este esquema es
DDL crudo compartido con motores que no son de acá):

1. **`version_table` propia.** `libracore-migrar` corre contra **esta misma
   base** —en VentaLibra el schema del core y el del dominio conviven, porque
   `base_core_separada` es `False`— y usa `alembic_version`. Compartir el nombre
   haría que cada cadena leyera la revisión de la otra: la del motor vería
   `0001_baseline_ventalibra`, no la reconocería, y el deploy moriría. Va
   `alembic_version_ventalibra`, que es la convención que ya usan LibraDesk,
   Gestiolibra y MedLibra.

2. **`target_metadata = None`.** No hay modelos de los que autogenerar: la
   fuente de verdad son las seis `init_*_schema()` de `app/db.py`, `CREATE
   TABLE` crudo. `alembic revision --autogenerate` **no sirve acá** y va a
   producir una revisión vacía — las revisiones se escriben a mano.

3. **No hay modo offline.** `alembic upgrade --sql` no puede emitir nada útil:
   la baseline **ejecuta Python** que inspecciona la base antes de decidir el
   DDL (`init_commerce_schema` corre su propio runner de migraciones, e
   `init_modules_schema` siembra filas leyendo `plans.TODOS_LOS_MODULOS`). Un
   `--sql` que emitiera algo estaría mintiendo, así que corta. Es la misma
   decisión que tomó el `env.py` de LibraCore.

El destino sale de `url_de_instancia("ventalibra")`, que es **el mismo lugar**
del que lo lee `app/asgi.py`. Es a propósito: si la cadena resolviera la base
por su cuenta, podría migrar una y el producto servir otra, sin fallar.
"""
from alembic import context
from sqlalchemy import engine_from_config, pool

from libracore.db import core
from libracore.db.url_de_instancia import url_de_instancia

target_metadata = None
VERSION_TABLE = "alembic_version_ventalibra"


def destino() -> str:
    """El destino tal como lo nombra el producto, sin tocarle el driver.

    🔑 Se resuelve UNA vez y lo usan los dos consumidores: `core.configure()` y
    el bind del engine. Tenerlos por caminos distintos era un desvío real: si
    `url_de_instancia` no encontraba nada y el destino salía del `alembic.ini`,
    `configure()` recibía la cadena vacía y el DDL decidía `is_postgres()` sobre
    una configuración que no era la de la base que estaba migrando — y eso deja
    un schema distinto del de producción **sin fallar**.
    """
    url = url_de_instancia("ventalibra") or context.config.get_main_option(
        "sqlalchemy.url", default=""
    )
    if not url or url.startswith("postgresql://user:password@"):
        raise RuntimeError(
            "Falta la URL de la base de VentaLibra: definí "
            "VENTALIBRA_DATABASE_URL. Sin eso no hay base contra la cual migrar "
            "(el `sqlalchemy.url` del alembic.ini es un placeholder a propósito)."
        )
    return url


def url_sqlalchemy(destino_: str) -> str:
    """El mismo destino, con el driver que la familia sí instala.

    SQLAlchemy resuelve `postgresql://` a psycopg2 y acá el driver es psycopg 3.
    Mismo arreglo que `libracore.migrar.normalizar_url`, y sólo para el bind:
    `core.configure()` recibe la forma original, que es la que el resto del
    producto usa.
    """
    if destino_.startswith("postgresql://"):
        return "postgresql+psycopg://" + destino_[len("postgresql://"):]
    return destino_


def run_migrations_online() -> None:
    d = destino()
    # 🔴 `configure` ANTES de abrir nada. Las revisiones llaman a código de
    # `libracommerce.db`, que decide parte del DDL mirando `core.is_postgres()`.
    # Si esa configuración y el bind no coinciden, el schema sale distinto del
    # de producción **sin fallar**.
    #
    # Se configura con la base **del dominio**, que es contra la que migra esta
    # cadena. En este producto es además la misma que la del core, porque
    # `base_core_separada` es `False`.
    core.configure(db_path=d)

    configuration = context.config.get_section(context.config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url_sqlalchemy(d)
    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError(
        "El modo offline (--sql) no está soportado: la baseline ejecuta "
        "init_schema_propio() e init_commerce_schema(), que inspeccionan la "
        "base antes de decidir el DDL."
    )

run_migrations_online()
