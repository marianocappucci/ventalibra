"""El huso horario del ecosistema: Argentina, UTC-3 fijo, sin horario de verano.

Regla del proyecto (`wiki/concepts/estandares-desarrollo.md`, seccion "Fecha y
hora"). Esta guarda existe porque el defecto **no da error**: hasta el
2026-08-23 los contenedores de este producto corrian en UTC y la suite estaba
entera en verde. Lo unico que se veia era el reloj 3 h adelantado, y una vez por
dia --- entre las 21:00 y la medianoche --- `date.today()` devolviendo manana:
una factura fechada el dia siguiente, un cierre de caja del lado equivocado.

Se chequean las dos mitades por separado, porque fallan por separado:

  1. el proceso que corre la suite;
  2. lo que declaran el Dockerfile y el compose, que es lo que le fija la zona
     al contenedor de produccion --- y que ningun test que mire solo el reloj
     del proceso puede detectar.
"""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

TZ = "America/Argentina/Buenos_Aires"
OFFSET = timedelta(hours=-3)
RAIZ = Path(__file__).resolve().parents[1]


def test_el_proceso_de_la_suite_corre_en_hora_de_argentina():
    """No se compara la FECHA a proposito.

    `datetime.now().date() == fecha_en_argentina()` da verdadero 21 de las 24
    horas del dia aunque el proceso este en UTC: se cumpliria por la razon
    equivocada y no serviria de guarda. El offset, en cambio, esta mal siempre
    que la zona este mal.
    """
    assert datetime.now().astimezone().utcoffset() == OFFSET


def test_el_dockerfile_le_fija_la_zona_a_la_imagen():
    assert "ENV TZ=" + TZ in (RAIZ / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.parametrize("declaracion", ["TZ: " + TZ, "- TZ=" + TZ])
def test_el_compose_le_fija_la_zona_a_los_dos_servicios(declaracion):
    """Uno por estilo: el sidecar de PostgreSQL usa mapping y la app, lista.

    El sidecar cuenta tanto como la app: es el que define que es "hoy" para un
    `CURRENT_DATE` o un default del schema.
    """
    assert declaracion in (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
