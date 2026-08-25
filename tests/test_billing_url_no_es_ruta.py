"""`configure()` no tiene que crear carpetas cuando la base es PostgreSQL.

El defecto real (2026-08-10, al cortar la demo): `configure()` hacia
`os.makedirs(os.path.dirname(db_path))` sin mirar el valor, y con una URL
`postgresql://usuario:clave@host:5432/base` eso crea el directorio
`postgresql:/usuario:clave@host:5432`. **La contrasena queda escrita en el
nombre de una carpeta**, y en `dev` -donde el repo esta bind-mounteado en
`/app`- la carpeta cae dentro del checkout del VPS y el siguiente
`docker build` la mete en la imagen.

El test se para en lo que el defecto DEJA -- una carpeta que no deberia
existir-, no en el valor de retorno: la funcion devuelve `None` con el defecto
puesto y sin el.
"""
from pathlib import Path

from app.services import billing


URL = "postgresql://ventalibra:una-clave-secreta@ventalibra-postgres:5432/ventalibra"


def test_una_url_de_postgres_no_deja_carpetas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # `configure()` sigue de largo e intenta conectarse; lo que se prueba es lo
    # que paso ANTES de eso, asi que el fallo de conexion no importa -- pero
    # tampoco se EXIGE. La primera version de este test envolvia la llamada en
    # `pytest.raises(Exception)` y quedo verde por un `AttributeError` de un
    # libracore viejo del venv: la carpeta nunca se llego a chequear.
    try:
        billing.configure(URL)
    except Exception:
        pass

    quedaron = [p for p in Path(tmp_path).rglob("*") if p.is_dir()]
    assert quedaron == [], (
        f"se crearon carpetas a partir de la URL: {[str(p) for p in quedaron]}"
    )
    # Y la parte que importa de verdad: la clave no quedo escrita en el disco.
    assert not any("una-clave-secreta" in str(p) for p in Path(tmp_path).rglob("*"))


def test_una_ruta_de_archivo_se_rechaza(tmp_path, monkeypatch):
    """El contrapeso, con el invariante nuevo.

    Hasta el 2026-08-25 este test exigia lo contrario: que una ruta de archivo
    CREARA su carpeta, porque el producto todavia podia arrancar sobre SQLite.
    Ya no puede --- `configure()` rechaza cualquier destino que no sea una URL
    de PostgreSQL, y el modo SQLite se retiro el 2026-08-12.

    Sigue siendo el contrapeso del test de arriba, y por el mismo motivo: sin
    el, una `configure()` que rechazara TODO --- incluida la URL --- pasaria
    aquel igual, porque tampoco dejaria carpetas.
    """
    import pytest

    monkeypatch.chdir(tmp_path)
    destino = tmp_path / "una" / "carpeta" / "nueva" / "core.db"

    with pytest.raises(RuntimeError, match="solo sobre PostgreSQL"):
        billing.configure(str(destino))

    # Y no alcanzo a crear nada antes de rechazar.
    assert not destino.parent.exists()
