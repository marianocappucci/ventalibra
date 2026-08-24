"""El huso horario del ecosistema: Argentina, UTC-3 fijo, sin horario de verano.

Regla del proyecto (`wiki/concepts/estandares-desarrollo.md`, sección "Fecha y
hora"). Esta guarda existe porque el defecto **no da error**: hasta el
2026-08-23 los contenedores de este producto corrían en UTC y la suite estaba
entera en verde. Lo único que se veía era el reloj 3 h adelantado, y una vez por
día — entre las 21:00 y la medianoche — `date.today()` devolviendo mañana: una
factura fechada el día siguiente, un cierre de caja del lado equivocado.

Se chequean tres cosas por separado, porque fallan por separado:

  1. el proceso que corre la suite;
  2. lo que declara el Dockerfile, que hace la imagen correcta por sí sola;
  3. lo que declara el compose para la app **y para el servidor PostgreSQL**.

🔴 **Lo tercero tiene dos mitades, y una es fácil de dar por hecha.** Al sidecar
no le alcanza con `TZ`: la imagen de PostgreSQL escribe `timezone` en
`postgresql.conf` UNA vez, en el `initdb`, y ese archivo vive en el volumen de
datos. Sobre un volumen que ya existe, `TZ` cambia el `date` del contenedor y no
cambia nada de lo que hace el servidor — `now()` sigue devolviendo UTC. Y `now()`
es el reloj que estampa los `server_default=func.now()`, así que quedaba
desfasado del reloj del proceso justo después de "arreglarlo".

Se midió: con `TZ` puesta y sin `command:`, `date` adentro del contenedor decía
`-03` y `select now()` seguía dando la hora de Londres. Por eso el chequeo
pregunta por `-c timezone=`, que es lo que sí lo fija.
"""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

TZ = "America/Argentina/Buenos_Aires"
OFFSET = timedelta(hours=-3)
RAIZ = Path(__file__).resolve().parents[1]


def test_el_proceso_de_la_suite_corre_en_hora_de_argentina():
    """No se compara la FECHA a propósito.

    `datetime.now().date() == fecha_en_argentina()` da verdadero 21 de las 24
    horas del día aunque el proceso esté en UTC: se cumpliría por la razón
    equivocada y no serviría de guarda. El offset, en cambio, está mal siempre
    que la zona esté mal.
    """
    assert datetime.now().astimezone().utcoffset() == OFFSET


def test_el_dockerfile_le_fija_la_zona_a_la_imagen():
    assert "ENV TZ=" + TZ in (RAIZ / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.parametrize("declaracion", [
    pytest.param("- TZ=" + TZ, id="la app, por variable de entorno"),
    pytest.param("TZ: " + TZ, id="el sidecar, por variable de entorno"),
    pytest.param("command: postgres -c timezone=" + TZ,
                 id="el SERVIDOR PostgreSQL, que es lo que TZ no alcanza a mover"),
])
def test_el_compose_fija_la_zona_donde_hace_falta(declaracion):
    assert declaracion in (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
