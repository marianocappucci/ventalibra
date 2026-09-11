"""La revision `0002_created_at_hora_ar`: lo que estampa `sale_mp_orders.created_at`.

🔑 **Se mide lo que el DEFAULT ESTAMPA, no el texto del DDL.** Se lee la
expresion que quedo en el catalogo y se la evalua: eso es lo que va a escribir
el proximo INSERT. Comparar el texto del DEFAULT contra otro texto compartiria
el instrumento con lo que se quiere controlar, porque los dos salen de la misma
traduccion del adaptador.

Y se corre por los dos caminos que tiene una instancia: el alta (la cadena
sobre una base vacia) y una instancia existente (el DEFAULT viejo, la cadena en
la baseline, y `alembic upgrade head` como en un deploy). El `downgrade` se
ejercita tambien: una revision cuyo rollback nadie corrio no tiene rollback.
"""
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone

import psycopg

from tests.motor_de_test import TEST_DATABASE_URL, limpiar_entre_tests
from tests.test_schema_propio_congelado import _correr_la_cadena

AR = timezone(timedelta(hours=-3))

#: El formato de texto de las columnas con reloj de la familia.
FORMATO = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def _url() -> str:
    return TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _lo_que_estampa() -> str:
    with psycopg.connect(_url()) as conexion:
        (expresion,) = conexion.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'sale_mp_orders' "
            "AND column_name = 'created_at'"
        ).fetchone()
        (valor,) = conexion.execute(f"SELECT ({expresion})::text").fetchone()
    return valor


def _alembic(*args: str) -> None:
    entorno = os.environ.copy()
    entorno["VENTALIBRA_DATABASE_URL"] = TEST_DATABASE_URL
    entorno["VENTALIBRA_LIBRACORE_DATABASE_URL"] = TEST_DATABASE_URL
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run(["alembic", *args], cwd=raiz, capture_output=True, text=True, env=entorno)
    assert r.returncode == 0, (r.stderr or r.stdout)[-2000:]


def _es_la_hora_de_argentina(valor: str) -> None:
    assert FORMATO.match(valor), f"el DEFAULT estampa {valor!r}, no el formato de la familia"
    estampado = datetime.strptime(valor, "%Y-%m-%d %H:%M:%S").replace(tzinfo=AR)
    assert abs(estampado - datetime.now(AR)) < timedelta(minutes=5), (
        f"el DEFAULT estampa {valor!r}, que no es la hora de Argentina"
    )


def test_un_alta_nace_estampando_la_hora_de_argentina():
    limpiar_entre_tests()
    _correr_la_cadena()
    _es_la_hora_de_argentina(_lo_que_estampa())


def test_la_revision_arregla_una_instancia_existente_y_el_downgrade_la_deja_como_estaba():
    limpiar_entre_tests()
    _correr_la_cadena()
    # El estado de una instancia de antes de esta revision: el DEFAULT viejo y la
    # cadena propia parada en la baseline.
    with psycopg.connect(_url(), autocommit=True) as conexion:
        conexion.execute(
            "ALTER TABLE sale_mp_orders ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP"
        )
        conexion.execute(
            "UPDATE alembic_version_ventalibra SET version_num = '0001_baseline_ventalibra'"
        )
    # 🔴 Control: el estado viejo SI tiene la forma que el arreglo cambia. Sin
    # esto, el test pasaria igual contra una revision que no hace nada.
    antes = _lo_que_estampa()
    assert not FORMATO.match(antes), antes

    _alembic("upgrade", "head")
    _es_la_hora_de_argentina(_lo_que_estampa())

    _alembic("downgrade", "0001_baseline_ventalibra")
    assert not FORMATO.match(_lo_que_estampa())
