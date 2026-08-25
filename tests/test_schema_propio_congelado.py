"""La cadena de Alembic y el arranque tienen que dejar el MISMO schema.

Este archivo nace el 2026-08-25, con la cadena propia de VentaLibra. Sostiene
las dos mitades del trato que hace `app/schema_propio.py`:

1. **Que las dos puntas no diverjan.** El arranque (`db.connect()`) y la
   baseline (`migrations/versions/0001_baseline_ventalibra.py`) llaman a la
   misma función hoy. El día que alguien agregue una `init_*_schema()` nueva a
   una sola de las dos —o re-exprese el DDL adentro de una revisión— las dos
   puntas empiezan a contar historias distintas y **no falla nada**: las
   instancias nuevas nacen de una y las viejas se migran con la otra.

2. **Que la secuencia declarada funcione sobre una base vacía**, que es el caso
   de un alta: ahí las migraciones corren ANTES del primer arranque, así que no
   hay `connect()` que les haya dejado nada puesto.

🔑 **Ninguno de los dos lee el fuente de la revisión.** Un guard que busque
`init_schema_propio` en el texto del archivo pasa en verde con la llamada
adentro de un `if False:`. Lo que se compara es el **schema que queda en la
base**.

🔑 **Y se corren los comandos DECLARADOS, no una copia.** `_correr_la_cadena`
lee `get_config().migraciones` y ejecuta esos comandos por `subprocess`, igual
que el deploy. Escribir acá `["alembic", "upgrade", "head"]` a mano habría hecho
pasar el test con la declaración del deploy vacía o en otro orden — que es
justamente el defecto que tumbó la demo de LibraClub.
"""
import importlib
import os
import subprocess

import psycopg

from tests.motor_de_test import TEST_DATABASE_URL, limpiar_entre_tests

#: Las tablas que esta cadena gobierna.
#:
#: ⚠️ **`modulos` NO está**, aunque `init_schema_propio()` la cree. La declaran
#: las dos —`init_core_schema()` de LibraCore y el `init_modules_schema()` de
#: acá— con `CREATE TABLE IF NOT EXISTS`, así que la crea la que corra primero.
#: Por el camino de la cadena eso es siempre LibraCore; por el camino del
#: arranque en un test, que no corre el motor, es la de acá. Meterla en esta
#: comparación pondría el test en rojo por una ambigüedad que existe desde antes
#: y que esta cadena no introduce. Ver `app/schema_propio.py`.
TABLAS_PROPIAS = (
    "party_billing",
    "party_roles",
    "sale_mp_orders",
    "sequences",
    "users",
)


def _schema_de_las_propias() -> str:
    """Las columnas de las tablas propias, en texto canónico y ordenado.

    Se leen del catálogo y no de un `pg_dump`: el dump trae el orden de creación
    y los nombres de constraint autogenerados, que cambian sin que el schema
    cambie y convertirían este test en ruido.

    Con `psycopg` directo y no por la conexión de la app: acá se está midiendo
    lo que quedó en la base, y usar el mismo objeto que lo creó es compartir el
    instrumento con lo que se quiere controlar.
    """
    with psycopg.connect(
        TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    ) as conexion:
        filas = conexion.execute(
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = ANY(%s) "
            "ORDER BY table_name, column_name",
            (list(TABLAS_PROPIAS),),
        ).fetchall()

    # 🔴 El control que impide el falso verde más barato de todos: si las dos
    # rutas fallaran y dejaran la base vacía, comparar dos strings vacíos daría
    # verde. Se exige que estén TODAS, no "algunas".
    presentes = {f[0] for f in filas}
    assert presentes == set(TABLAS_PROPIAS), (
        f"faltan tablas propias en la base: encontradas {sorted(presentes)}, "
        f"esperadas {sorted(TABLAS_PROPIAS)}. Comparar un schema parcial no "
        "prueba nada."
    )
    return "\n".join(
        f"{t}.{c} {tipo} nullable={nul} default={dflt!r}" for t, c, tipo, nul, dflt in filas
    )


def _version(tabla: str):
    with psycopg.connect(
        TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    ) as conexion:
        return conexion.execute(f"SELECT version_num FROM {tabla}").fetchall()


def _correr_la_cadena():
    """Los comandos que el producto DECLARA, en orden, como los corre el deploy.

    `VENTALIBRA_DATABASE_URL` se pasa explícita al subproceso: la suite nombra
    su base con `VENTALIBRA_TEST_DATABASE_URL`, y `migrations/env.py` la resuelve
    —igual que `app/asgi.py`— con `url_de_instancia("ventalibra")`. Sin este
    puente la cadena migraría otra base, o ninguna.
    """
    from libracore.provisioning import get_config

    importlib.reload(importlib.import_module("scripts.panel_admin"))
    declarados = get_config().migraciones
    assert declarados, (
        "el producto no declara `migraciones`: la cadena existe pero no la corre "
        "nadie en el deploy, que es el defecto que tumbó la demo de LibraClub."
    )

    entorno = os.environ.copy()
    entorno["VENTALIBRA_DATABASE_URL"] = TEST_DATABASE_URL
    entorno["VENTALIBRA_LIBRACORE_DATABASE_URL"] = TEST_DATABASE_URL

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for comando in declarados:
        r = subprocess.run(
            list(comando), cwd=raiz, capture_output=True, text=True, env=entorno
        )
        assert r.returncode == 0, (
            f"falló `{' '.join(comando)}` sobre una base vacía:\n"
            f"{(r.stderr or r.stdout)[-2000:]}"
        )


def test_la_secuencia_declarada_levanta_el_schema_desde_cero():
    """El caso del alta: base vacía, migraciones, y recién después la app.

    🔴 El orden no es decorativo: `party_billing` y `party_roles` referencian
    `parties` y `sale_mp_orders` referencia `sales`, las tres de LibraCommerce —
    que no tiene cadena. Por eso la baseline llama a `init_commerce_schema()`
    ella misma, y por eso `libracore-migrar` va primero en la declaración.
    """
    limpiar_entre_tests()
    _correr_la_cadena()

    assert [f[0] for f in _version("alembic_version_ventalibra")] == [
        "0001_baseline_ventalibra"
    ]
    _schema_de_las_propias()  # exige que estén las cinco


def test_la_baseline_y_el_arranque_dejan_el_mismo_schema():
    """El invariante que hace que la cadena sirva para algo.

    Una instancia **nueva** nace de la cadena. Una instancia **vieja** tiene el
    schema que le dejó `connect()` hace meses. Si las dos puntas no coinciden,
    el parque queda con dos esquemas distintos y la próxima revisión corre sobre
    el que no esperaba.
    """
    limpiar_entre_tests()
    _correr_la_cadena()
    por_la_cadena = _schema_de_las_propias()

    from app import db

    limpiar_entre_tests()
    conn = db.connect(TEST_DATABASE_URL)
    try:
        por_el_arranque = _schema_de_las_propias()
    finally:
        conn.close()

    assert por_la_cadena == por_el_arranque, (
        "la baseline y el arranque dejan esquemas distintos. Es el defecto que "
        "este archivo existe para atajar: las instancias nuevas nacen de la "
        "cadena y las viejas del arranque.\n"
        f"--- cadena ---\n{por_la_cadena}\n--- arranque ---\n{por_el_arranque}"
    )


def test_las_dos_cadenas_no_comparten_la_tabla_de_version():
    """`alembic_version_ventalibra` para la propia, `alembic_version` para el motor.

    🔴 Acá las dos cadenas corren contra la MISMA base —`base_core_separada` es
    `False` en este producto—, así que compartir el nombre haría que cada una
    leyera la revisión de la otra: la del motor encontraría
    `0001_baseline_ventalibra`, no la reconocería, y el deploy moriría.
    """
    limpiar_entre_tests()
    _correr_la_cadena()

    del_motor = _version("alembic_version")[0][0]
    propia = _version("alembic_version_ventalibra")[0][0]

    assert propia == "0001_baseline_ventalibra"
    assert del_motor != propia, (
        "las dos cadenas escribieron la misma revisión: están compartiendo la "
        "tabla de versión."
    )
    assert del_motor.startswith("000"), (
        f"la tabla del motor quedó en {del_motor!r}, que no parece una revisión "
        "de LibraCore"
    )
