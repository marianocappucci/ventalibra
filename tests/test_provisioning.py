"""El provisioning de este producto, atado al código que corre.

Nace el 2026-08-24, de medir los ocho productos de la familia: **seis de ocho**
tenían los dos `configure()` diciendo cosas distintas, siempre en el mismo campo.
Los dos que no divergían eran justamente los dos que ya tenían este archivo.
"""

import importlib


def test_los_dos_scripts_configuran_LO_MISMO():
    """El desvío que el comentario de los dos archivos promete que no existe.

    `scripts/nuevo_cliente.py` y `scripts/panel_admin.py` llaman los dos a
    `configure()`, que pisa un `_cfg` **global**, y `libracore.admin.services`
    importa los dos módulos en el mismo proceso. Si dicen cosas distintas, cuál
    gana depende del orden de los imports — o sea que la misma operación sale
    distinta según qué se haya importado antes en ese proceso.

    **Este test nace en rojo.** Al escribirlo, `panel_admin.py` pasaba
    `backup_zip=True` y `nuevo_cliente.py` no.

    Se compara la configuración **entera** con `asdict`, no campo por campo: un
    test que mirara sólo `backup_zip` dejaría pasar el próximo desvío, que va a
    ser en otro campo.
    """
    from dataclasses import asdict

    from libracore.provisioning import get_config

    def config_de(script):
        importlib.reload(importlib.import_module(f"scripts.{script}"))
        return asdict(get_config())

    uno = config_de("nuevo_cliente")
    otro = config_de("panel_admin")

    distintos = {k: (uno[k], otro[k]) for k in uno if uno[k] != otro[k]}
    assert not distintos, f"los dos scripts configuran distinto: {distintos}"
