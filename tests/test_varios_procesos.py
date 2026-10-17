"""El arranque de VentaLibra con DOS workers de uvicorn de verdad (libracore ADR-044).

Todo el producto sigue corriendo con **un** proceso (`WEB_CONCURRENCY` por defecto, 1), pero el código ya está listo para
más. Lo único que un `TestClient` no puede ver es lo que pasa cuando dos procesos arrancan JUNTOS contra las mismas
bases: `create_app()` ES el arranque, y todo lo que corre ahí —el DDL de `db.connect()` y de `billing.configure()`, las
sucursales y cajas mínimas, el admin— es un «si no existe, crear» que los dos workers contestan «no existe» antes de que
ninguno haya creado, salvo que los serialice `una_vez_al_arrancar`.

Cada test deja las bases como las deja una etapa del alta y levanta `uvicorn app_dos_workers:app --workers 2` (`app.asgi`
con la ventana de la carrera ensanchada, ver `tests/app_dos_workers.py`) como subproceso. Después mira que:

- los dos workers arrancan, sin ningún traceback en el log (los dos loguean «Application startup complete»; uvicorn
  reinicia a un worker que muere, así que «arrancaron» no alcanza);
- queda UN solo admin, UNA sucursal con UN depósito, UNA caja y cada módulo UNA vez.

Los dos puntos de partida:

- **base vacía** (sólo el esquema de auth): el primer arranque crea todo, el DDL propio incluido. Es donde dos
  `CREATE TABLE IF NOT EXISTS` de la misma tabla chocan en el catálogo de PostgreSQL.
- **como el deploy** (las cadenas declaradas por `scripts/panel_admin.py` ya corridas, sin sembrar): el esquema está,
  falta lo que siembra el arranque.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psycopg
import pytest
from libracore.testing.varios_procesos import pedir, puerto_libre
from motor_de_test import TEST_DATABASE_URL, limpiar_entre_tests

from plans import TODOS_LOS_MODULOS
from tests.test_schema_propio_congelado import _correr_la_cadena

pytestmark = pytest.mark.varios_procesos

RAIZ = Path(__file__).resolve().parent.parent


def _cruda(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _esperar(proceso, log, base, *, arranque=120.0):
    """Hasta que `/health` conteste Y los dos workers hayan terminado su startup (el segundo espera el candado)."""
    limite = time.monotonic() + arranque
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            break
        log.seek(0)
        listos = len(re.findall(r"Application startup complete", log.read().decode(errors="replace")))
        if listos >= 2:
            try:
                if pedir(base + "/health", espera=2)[0] == 200:
                    return
            except OSError:
                pass
        time.sleep(0.2)
    log.seek(0)
    raise AssertionError("los dos workers no terminaron de arrancar:\n" + log.read().decode(errors="replace"))


def _arrancar_dos_workers(tmp_path) -> str:
    """Levanta uvicorn con 2 workers sobre `TEST_DATABASE_URL`, espera que arranquen y devuelve el log (ya sin servidor)."""
    puerto = puerto_libre()
    env = {
        **os.environ, "PYTHONPATH": str(RAIZ / "tests"), "ENV": "development", "DATA_DIR": str(tmp_path / "data"),
        "VENTALIBRA_DB_PATH": TEST_DATABASE_URL, "VENTALIBRA_LIBRACORE_DB_PATH": TEST_DATABASE_URL,
    }
    with tempfile.TemporaryFile() as log:
        proceso = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app_dos_workers:app", "--host", "127.0.0.1", "--port", str(puerto),
             "--workers", "2", "--log-level", "info"],
            env=env, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            _esperar(proceso, log, f"http://127.0.0.1:{puerto}")
        finally:
            proceso.terminate()
            try:
                proceso.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait()
        log.seek(0)
        return log.read().decode(errors="replace")


def _verificar(texto: str) -> None:
    # 🔴 uvicorn REINICIA a un worker que muere en el arranque: sin esto, un worker que revienta por la carrera y vuelve a
    # levantar limpio pasaría por «arrancó bien». Un arranque sano no deja ningún traceback en el log.
    assert "Traceback" not in texto and "startup failed" not in texto, texto
    with psycopg.connect(_cruda(TEST_DATABASE_URL)) as c:
        cuenta = lambda sql: c.execute(sql).fetchone()  # noqa: E731
        admins = cuenta("SELECT count(*) FROM usuarios WHERE role = 'admin'")[0]
        modulos = cuenta("SELECT count(*), count(DISTINCT modulo) FROM modulos")
        sucursales = cuenta("SELECT count(*) FROM branches")[0]
        depositos = cuenta("SELECT count(*) FROM locations")[0]
        cajas = cuenta("SELECT count(*), count(*) FILTER (WHERE es_default = 1) FROM cajas")
    assert admins == 1, f"{admins} admins: el hook de arranque corrió sin candado en los dos workers"
    assert modulos == (len(TODOS_LOS_MODULOS), len(TODOS_LOS_MODULOS))
    assert sucursales == 1, f"{sucursales} sucursales: la siembra mínima corrió sin candado en los dos workers"
    assert depositos == 1, f"{depositos} depósitos"
    assert cajas == (1, 1), f"{cajas[0]} cajas ({cajas[1]} por defecto)"


def test_dos_workers_arrancan_sobre_una_base_vacia(tmp_path):
    limpiar_entre_tests()          # sólo el esquema de auth: el primer arranque crea todo lo demás
    _verificar(_arrancar_dos_workers(tmp_path))


def test_dos_workers_arrancan_sobre_la_base_que_deja_el_deploy(tmp_path):
    limpiar_entre_tests()
    _correr_la_cadena()            # libracore-migrar, libraauth-migrar, libracommerce-migrar, alembic: sin sembrar
    _verificar(_arrancar_dos_workers(tmp_path))
