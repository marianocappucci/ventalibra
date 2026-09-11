"""Ningun DEFAULT del DDL de VentaLibra estampa una hora que no sea la de Argentina.

Es la guarda que Contalibra y Restolibra tienen desde el 2026-08-29 (ver la
revision `0003` de [[libracore]] para el diagnostico: el DEFAULT de las columnas
con reloj estampaba UTC, y lo creado entre las 21:00 y la medianoche quedaba
fechado el dia siguiente). Llego a este producto el 2026-09-11, con el chequeo
de VentaLibra contra esos dos, y encontro una columna:
`sale_mp_orders.created_at`, con `DEFAULT CURRENT_TIMESTAMP`. La arregla la
revision `0002_created_at_hora_ar`, que explica por que esa cara del defecto es
distinta de la de Restolibra.

🔑 **El barrido vive en el motor, no aca.** `defaults_fuera_de_hora_ar()` es la
misma funcion que corren LibraCore y los otros productos con DDL propio.
Copiar la regex en cada repo es la forma conocida de que empiecen a decir cosas
distintas.

🔑 **Y mira la PROPIEDAD final**, no el patron viejo: "ninguna columna con reloj
queda fuera de la hora de Argentina". Buscar `datetime('now')` habria dejado
pasar justo la de este producto, que estaba escrita como `CURRENT_TIMESTAMP`.
"""
from pathlib import Path

import pytest
from libracore.db.schema import defaults_con_reloj, defaults_fuera_de_hora_ar

RAIZ = Path(__file__).resolve().parents[1]

#: Se barren los directorios, no una lista de archivos escrita a mano: un DDL
#: nuevo en un modulo nuevo tiene que entrar solo. Las revisiones ya aplicadas
#: quedan afuera porque son historia y no se tocan.
_DIRECTORIOS = ("app",)
_EXCLUIR = ("__pycache__", "/migrations/versions/", "/tests/")


def _fuentes():
    for sub in _DIRECTORIOS:
        for archivo in sorted((RAIZ / sub).rglob("*.py")):
            if any(x in str(archivo) for x in _EXCLUIR):
                continue
            yield archivo


def test_el_barrido_encuentra_el_ddl():
    """Control: sin esto, una lista vacia pasaria por verde para siempre.

    Un barrido que dejo de encontrar archivos —porque el DDL se movio de
    carpeta, por ejemplo— informa "limpio" sobre un repo que no miro. Este
    producto tiene UNA columna con reloj en su DDL propio (`app/db.py`), asi
    que el piso es uno.
    """
    encontradas = sum(
        len(defaults_con_reloj(f.read_text(encoding="utf-8"))) for f in _fuentes()
    )
    assert encontradas >= 1, f"el barrido encontro {encontradas} columnas con reloj"


@pytest.mark.parametrize("archivo", sorted(_fuentes()), ids=lambda f: f.name)
def test_ninguna_columna_estampa_una_hora_que_no_sea_la_de_argentina(archivo):
    fuera = defaults_fuera_de_hora_ar(archivo.read_text(encoding="utf-8"))
    assert fuera == [], (
        f"{archivo.relative_to(RAIZ)} declara columnas con una hora que no es la "
        "de Argentina:\n" + "\n".join(fuera)
    )
