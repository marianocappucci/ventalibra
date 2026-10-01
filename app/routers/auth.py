"""Router /auth (login/logout/me/verify) -- shim sobre
libraauth.session_auth.build_json_api_auth_router.

Extraído 2026-07-26 a libracore.auth (era byte-idéntico en Gestiolibra/
MedLibra/VentaLibra, ver wiki/analyses/auditoria-duplicacion-familia-libra.md)
y **migrado el 2026-07-30 a libraauth**: VentaLibra ya no importa nada de
`libracore.auth`.

`incluir_verify=True` es obligatorio acá: `POST /auth/verify` es el chequeo
stateless de credenciales que usa el login de `/docs/` de la landing
(server-to-server con `DOCS_AUTH_SECRET`, ver ADR-018). En libraauth el
endpoint es opt-in porque no todo consumidor tiene landing; **sin este flag el
`/docs/` de la landing deja de poder validar credenciales**.
"""
import json
import logging

from libraauth.session_auth import build_json_api_auth_router
from libracore import config_manager

from plans import ADDONS, TODOS_LOS_MODULOS

from ..permisos import capacidades_de

logger = logging.getLogger(__name__)


def _extras(request, user) -> dict:
    """Lo que la SPA necesita saber de ESTA instancia y de quien entró, mas alla de `role`.

    **`capacidades`**: lo que el usuario puede hacer, segun su rol (ADR-049, `app/permisos.py`). La SPA decide
    con esto el menu y las rutas (`frontend/src/lib/permisos.ts`); antes miraba `user.role === 'admin'`, que con
    cinco roles no alcanza. Es la MISMA matriz que las guardas del backend (una sola fuente), asi que menu y
    403 no pueden discrepar. Sale de un diccionario en memoria: no puede fallar como la consulta de modulos.
    Sirve para decidir que mostrar, no para autorizar: el que corta es cada endpoint.

    **`modulos`**: los habilitados de ESTA instancia (los del plan en `TODOS_LOS_MODULOS` y los add-ons
    encendidos), la misma forma que ya usan LibraDesk y Contalibra. Sale en el usuario de `/auth/login` y
    `/auth/me` (ADR-048): sin esto la SPA no sabia que la facturacion ni las sucursales de mas son del plan
    Premium.

    Los modulos se leen en cada request y no al importar: el plan se cambia con la app corriendo
    (`aplicar_plan_en_db`) y un valor cacheado dejaria la pantalla ofreciendo lo que el backend ya rechaza.

    🔑 **Ante una falla NO devuelve una lista vacia de modulos: omite el campo.** Es el reves de LibraDesk, y a
    proposito: aca el gate de verdad es del backend (un 403 por endpoint) y la SPA tolera la falta del campo
    ofreciendo todo (ver `frontend/src/lib/modulos.ts`). Una lista vacia le esconderia a un cliente Premium la
    facturacion que pago porque una consulta fallo un instante."""
    extras: dict = {"capacidades": capacidades_de((user or {}).get("role"))}
    # El nombre del negocio, para el subtítulo de la barra lateral (igual que Contalibra, Restolibra y LibraDesk). Es la config de
    # LibraCore que edita Configuración; vacío = el campo no viaja y la SPA no dibuja subtítulo. Se lee el JSON a mano y NO con
    # `config_manager.load()`: ése resuelve además los secretos contra la base en cada login y cada `/auth/me`, y haría fallar la
    # autenticación si el almacén de secretos tiene un error, para leer un campo que no es secreto (hallazgo de Codex).
    try:
        with open(config_manager.CONFIG_PATH, encoding="utf-8") as f:
            nombre = (json.load(f).get("empresa_nombre") or "").strip()
    except Exception:
        nombre = ""
    if nombre:
        extras["empresa_nombre"] = nombre
    try:
        modulos = request.app.state.modules
        extras["modulos"] = sorted(m for m in TODOS_LOS_MODULOS | ADDONS if modulos.is_enabled(m))
    except Exception:
        logger.warning("No se pudieron leer los modulos para /auth: la SPA ofrece todo", exc_info=True)
    return extras


# `incluir_demo=True` NO enciende nada por si solo: `POST /auth/demo` se
# registra unicamente si la instancia ademas tiene `DEMO_MODE` y
# `DEMO_USERNAME` puestas. En las instancias de cliente la ruta no existe —
# es un 404, no un 403. Ver `_demo_username` en libraauth.
#
# `captcha=True`: captcha ALTCHA «No soy un robot» SIEMPRE, no recien despues
# de N fallos (decision del humano, 2026-09-11; ADR-014 de libraauth). Agrega
# `GET /auth/captcha` y vuelve obligatorio el campo `captcha` del login y del
# forgot-password. Va de la mano con `captchaPath` en frontend/src/pages/Login.tsx
# y PasswordReset.tsx, y con `iniciar_sesion` de scripts/seed_demo.py.
router = build_json_api_auth_router(
    incluir_verify=True, incluir_password_reset=True, incluir_demo=True, captcha=True,
    get_extras=_extras,
)
