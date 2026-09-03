"""La carpeta de backups no se deriva de la ruta de la base.

🔴 El defecto: salia de `os.path.dirname(libracore_db_path)`, y con la base en
PostgreSQL eso no es una carpeta. `dirname()` de
`postgresql://usuario:clave@host:5432/base` devuelve
`postgresql://usuario:clave@host:5432`, y ahi se creaba `backups/`: un
directorio **con la contrasena en el nombre**, colgando del directorio de
trabajo.

Se encontro en [[contalibra]] el 2026-08-10 -- ahi ademas afectaba a la carpeta
de los certificados de ARCA-- y este producto tenia el mismo patron sin guarda.
"""
import os

import pytest

from app.main import _carpeta_de_backups

URL = "postgresql://ventalibra:una-clave-secreta@ventalibra-postgres:5432/ventalibra"


def test_con_una_url_no_devuelve_una_ruta_derivada_de_ella(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/app/dev-data")

    destino = _carpeta_de_backups(URL)

    assert "://" not in destino, destino
    assert "@" not in destino, f"la clave quedo en la ruta: {destino!r}"
    assert "una-clave-secreta" not in destino
    assert destino == os.path.join("/app/dev-data", "backups")


@pytest.mark.parametrize("esquema", ["postgresql://", "postgresql+psycopg://"])
def test_reconoce_las_dos_formas_de_escribir_la_url(monkeypatch, esquema):
    """SQLAlchemy usa `postgresql+psycopg://` y el resto `postgresql://`. Si el
    chequeo mira sola una, la otra vuelve al camino de archivo."""
    monkeypatch.setenv("DATA_DIR", "/datos")
    destino = _carpeta_de_backups(f"{esquema}u:p@h:5432/base")
    assert destino == os.path.join("/datos", "backups")


def test_con_una_ruta_de_archivo_sigue_al_lado_de_la_base():
    """El contrapeso: sin esto, devolver siempre `DATA_DIR` tambien pasaria los
    tests de arriba y movería los backups de las instancias en SQLite."""
    assert _carpeta_de_backups("/app/dev-data/ventalibra_libracore.db") == os.path.join(
        "/app/dev-data", "backups"
    )
    assert _carpeta_de_backups("/otro/lado/core.db") == os.path.join("/otro/lado", "backups")
