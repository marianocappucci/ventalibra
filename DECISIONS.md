# Decisiones arquitectónicas — VentaLibra

Registro ADR. No borrar decisiones: si dejan de aplicar, marcarlas como
reemplazadas.

## ADR-001 — Componer LibraCommerce en vez de reimplementar catálogo/inventario/ventas

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: el roadmap de la familia Libra (`wiki/analyses/arquitectura-familia-libra-alcance.md`)
  ya define LibraCommerce como el motor reutilizable de catálogo, compras,
  inventario y ventas, con esquema SQLite y `SqliteCommerceRepository`
  estables (55 tests pasando al momento de esta decisión).
- Decisión: VentaLibra depende de `libracommerce` como paquete versionado
  (git tag), no copia ni reimplementa su dominio.
- Consecuencias: VentaLibra queda acoplado al ritmo de release de
  LibraCommerce; cualquier extensión de catálogo que otro vertical también
  necesite (código de barras, variantes, listas de precio) debe evaluarse
  primero como cambio en LibraCommerce, no como parche local.
- Alternativas descartadas: reimplementar un catálogo/inventario propio
  dentro de VentaLibra — descartado porque duplicaría exactamente lo que
  LibraCommerce ya resuelve y probó contra datos reales de Contalibra.

## ADR-002 — Tabla `users` propia en vez de `libracore.db.usuarios`

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: `libracore.db.usuarios` ya resuelve alta/baja/auth de usuarios
  contra SQLite, y VentaLibra (a diferencia de GestioLibra/MedLibra, que
  usan SQLAlchemy/Postgres para su dominio propio) es 100% SQLite nativo, así
  que técnicamente podría reusarlo sin el problema de acoplamiento que tienen
  esos dos productos.
- Decisión: VentaLibra mantiene su propia tabla `users` y su propio
  `security.py` (PBKDF2), igual que GestioLibra y MedLibra, en vez de
  importar `libracore.db.usuarios`.
- Consecuencias: se duplica por tercera vez el mismo algoritmo de hashing
  entre productos de la familia. Se acepta por consistencia — los tres
  verticales gestionan usuarios de la misma forma, y `SessionAuth` ya está
  diseñado para recibir callbacks en vez de asumir un esquema (no hay
  ganancia real de acoplarse al esquema de `usuarios` de LibraCore para
  esto).
- Alternativas descartadas: usar `libracore.db.usuarios` directamente contra
  la misma base sqlite de LibraCommerce — descartada por el motivo anterior;
  queda documentada como pregunta abierta para la Fase 3 (cuando además haga
  falta `init_core_schema` para caja/facturación, puede que sí valga la pena
  reconsiderarlo, ver `ROADMAP.md`).
- **Revisitado en Fase 3 (2026-07-25)**: con `libracore.db` ya en uso real
  (caja/facturación, ver ADR-007), se reconsideró y se mantuvo la decisión
  original — no hay ganancia real en migrar `users` a `libracore.db.usuarios`
  solo porque ahora existe esa segunda base; seguiría siendo la misma
  duplicación de PBKDF2 que ya se acepta, sin resolver nada. Pregunta cerrada.

## ADR-003 — Una sola base SQLite en Fase 1

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: `libracore.db.core` requiere configurarse contra un único
  `db_path` de proceso; MedLibra usa una segunda base SQLite dedicada
  exclusivamente para los módulos de LibraCore que la necesitan
  (`caja`/`arca_facturacion`), separada de su motor de dominio principal.
  VentaLibra en Fase 1 no usa ningún módulo de `libracore.db` todavía (solo
  `libracore.auth`, que no toca SQLite).
- Decisión: Fase 1 usa una única base SQLite (`data/ventalibra.db`) para
  LibraCommerce + `users`. La segunda base para LibraCore se suma recién en
  Fase 3, cuando haga falta.
- Consecuencias: evita complejidad prematura (dos conexiones, dos rutas de
  configuración) mientras no aporta valor real.
- Alternativas descartadas: adelantar la segunda base desde Fase 1 "por las
  dudas" — descartado, YAGNI.

## ADR-004 — Confirmar recepción de compra delega en `libracommerce.usecases`, no se reimplementa

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: en Fase 1, confirmar una venta (stock por línea de producto) se
  reimplementó dentro de `app/services/sales.py` porque LibraCommerce
  todavía no ofrecía esa orquestación (ver ADR-001 y el hallazgo de esa
  fase). Entre esa fase y esta, LibraCommerce agregó
  `libracommerce.usecases.sales.confirm_sale` y
  `libracommerce.usecases.purchasing.confirm_purchase_receipt` (v0.1.2) —
  la misma orquestación que antes faltaba, ahora resuelta upstream.
- Decisión: `PurchasingService.confirm_receipt` delega enteramente en
  `confirm_purchase_receipt`, sin reimplementar nada. Se aprovechó además
  para refactorizar `SaleService.confirm` (Fase 1) y que también delegue en
  `confirm_sale`, cerrando la duplicación que había quedado documentada en
  el wiki de LibraCommerce.
- Consecuencias: VentaLibra ya no mantiene dos copias de la misma lógica
  de negocio (una acá, otra en LibraCommerce) — cualquier cambio futuro a
  esa orquestación (ej. costo promedio ponderado en vez de last-cost) se
  hace una sola vez, en LibraCommerce, y llega acá con el próximo bump de
  versión.
- Alternativas descartadas: mantener la reimplementación propia de Fase 1
  "porque ya funciona" — descartado, es exactamente la duplicación que el
  propio wiki de LibraCommerce señaló como pendiente de resolver.

## ADR-005 — Secuencias propias (`sequences`), no reutilizar `local_sequences` de LibraCommerce

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: `_next_sale_number` (Fase 1) reusaba la tabla `local_sequences`
  del esquema de LibraCommerce como atajo, documentado explícitamente como
  "ya presente en el esquema, no colisiona". Al bumpear a `libracommerce`
  v0.1.2 para la Fase 2, esa tabla dejó de existir — era infraestructura
  interna de la especificación offline de LibraCommerce, retirada por
  completo al migrar esa responsabilidad a LibraEdge. Rompió los 5 tests
  del flujo de venta hasta corregirlo.
- Decisión: `app/db.py` gana su propia tabla `sequences` (`init_sequences_schema`/
  `next_sequence`), separada del esquema de LibraCommerce. La usan tanto
  `_next_sale_number` (Fase 1) como la numeración de órdenes de compra
  (Fase 2, `OC-000001`).
- Consecuencias: VentaLibra deja de depender de una tabla de implementación
  interna de una dependencia que no forma parte de su contrato público
  (`CommerceRepository`) — un futuro bump de `libracommerce` no puede volver
  a romper esto de la misma forma.
- Alternativas descartadas: seguir reusando `local_sequences` con otro
  nombre de secuencia si LibraCommerce la reintrodujera — descartado, ya
  demostró ser frágil una vez.

## ADR-006 — 401 intermitente en la suite: reloj de WSL2 inestable, no un bug de código (sin cambios de código)

- Estado: investigado y cerrado — no aplica ningún cambio de código
- Fecha: 2026-07-25
- Contexto: al validar Fase 2 corriendo la suite muchas veces (no solo una),
  apareció un `401 not authenticated` intermitente (~15-30% de las corridas
  completas) en medio de una sesión ya autenticada exitosamente. Reproducido
  en `test_sales.py`/`test_catalog.py`/`test_stock.py` (Fase 1, no tocado en
  esta ronda) y `test_purchasing.py`/`test_suppliers.py` (Fase 2) por igual —
  no es un bug de Compras. Confirmado también en GestioLibra (10 corridas,
  3 fallos, en módulos sin ninguna relación con VentaLibra).
- **Investigación fallida primero, documentada para no repetirla**: se probó
  (1) `threading.Lock()` en un middleware, (2) forzar
  `anyio.to_thread.current_default_thread_limiter()` a 1 token, (3)
  `anyio.Lock()` en el mismo middleware, y (4) convertir **todas** las
  dependencias/endpoints de auth a `async def` (eliminando por completo el
  despacho a threadpool de Starlette). Cada intento parecía funcionar en
  validaciones cortas, pero **ninguno sobrevivió una revalidación rigurosa**
  — incluida una falsa señal de "0 fallos en 50/80 corridas" que resultó ser
  un falso negativo: el detector de fallos solo buscaba la palabra `failed`
  en el resumen de pytest, pero un bug real introducido al mover
  `get_session_auth` a `async def` (se llama directamente, no vía `Depends`,
  en `routers/auth.py`) rompía el login con un error de **fixture** ("1
  error"), que no contiene la palabra `failed` y no lo detectaba el grep.
  Con todo async y el bug de fixture corregido, el 401 intermitente **seguía
  ocurriendo igual** — descartando threading/`anyio` como causa por completo.
- **Causa raíz real**: instrumentando `get_current_user` para capturar la
  excepción exacta de `itsdangerous`, apareció `SignatureExpired` con
  `date_signed` prácticamente idéntico al momento de la verificación (no
  vencido por ningún margen real — `max_age` es de 7 días). Un script de
  diagnóstico que monitorea `time.time()` en un loop con `sleep(0.005)`
  durante ~10s confirmó **saltos de reloj de ~15.18 segundos, hacia adelante
  y hacia atrás, de forma recurrente**, dentro del mismo proceso Python —
  el reloj virtualizado de este WSL2 se desincroniza del reloj del host y se
  resincroniza con saltos instantáneos (no un ajuste gradual). Cualquier
  comparación de timestamps de corta duración entre dos llamadas a
  `time.time()` separadas por unos segundos de trabajo real (exactamente el
  rango de duración de una corrida de pytest) puede toparse con uno de estos
  saltos y producir una firma que parece "expirada" o inválida sin ninguna
  relación con el código de la aplicación.
- **Decisión: no se aplica ningún cambio de código.** El problema es del
  entorno (reloj de WSL2 en esta máquina), no de `SessionAuth`, ni de
  VentaLibra, ni de ningún producto de la familia — revertidos todos los
  intentos de fix (async, locks, thread-limiter) a como estaba el código
  antes de esta investigación. Confirmado que el flaky sigue ocurriendo
  igual con el código revertido, cerrando el caso.
- Consecuencias: el flaky **puede seguir apareciendo** en corridas locales de
  la suite en este entorno específico mientras el reloj de WSL2 no se
  estabilice — no indica una regresión real si aparece de nuevo. Recomendado
  para el usuario, fuera del alcance de esta sesión: verificar la versión de
  WSL2 (`wsl --version` desde PowerShell) y considerar `wsl --update`, o
  revisar si hay suspensión/hibernación frecuente del host disparando la
  resincronización. Mismo diagnóstico aplica a GestioLibra/MedLibra/cualquier
  otro producto corriendo en esta misma máquina — no es específico de ningún
  repo.
- Alternativas descartadas: las cuatro variantes de "arreglar con código"
  listadas arriba — ninguna ataca la causa real, y añaden complejidad
  (middleware, locks, cambios de `def` a `async def` en 9 archivos) sin
  ningún beneficio real.

## ADR-007 — Facturación/caja con LibraCore: caja siempre, factura opcional por venta

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: MedLibra/Gestiolibra ya resolvieron este mismo problema para
  turnos — `app/services/billing.py` (segunda base SQLite dedicada a
  `libracore.db`, `arca_facturacion`, `caja`) es el patrón de referencia,
  portado a VentaLibra casi verbatim en la mecánica (`configure()`,
  `get_arca_config()`/`set_arca_config()`, `_tipo_comprobante()`,
  `_split_iva()` al 21% fijo). Pero el dominio de retail difiere del de
  turnos en dos puntos reales, resueltos con el usuario antes de codificar
  (mismo criterio que MedLibra ADR-016):
  1. **En retail no toda venta lleva factura** (a veces es solo ticket) —
     a diferencia de un turno completado, que siempre facturaba si tenía
     precio configurado y el módulo estaba habilitado.
  2. **El control de caja es independiente del tema fiscal** — un comercio
     necesita que TODA venta cobrada quede en caja, factures o no, mientras
     que MedLibra/Gestiolibra solo tocan caja cuando hay factura de por
     medio (seña/saldo de un turno).
- Decisión:
  - `POST /sales/{id}/confirm` suma `invoice: bool = False` (opt-in
    explícito por venta, no automático por tener CUIT cargado) y
    `medio_pago: str` (pasa a ser **requerido**, ya no opcional). El
    handler pasa a ser `async def` — necesario de verdad esta vez (no como
    el experimento revertido de ADR-006): `arca_facturacion.get_next_numero_with_arca`/
    `solicitar_cae` son corutinas reales que hacen `await` a WSAA/WSFE.
    Los demás handlers de `sales.py` siguen síncronos.
  - `billing.invoice_sale()` — sin seña/saldo: una sola factura por el
    total de la venta, tipo A si el cliente es Responsable Inscripto (vía
    la extensión `party_billing`), tipo B en cualquier otro caso incluido
    sin cliente asociado (factura como "Consumidor Final").
  - `billing.record_sale_payment()` — función separada de `invoice_sale`,
    llamada **siempre** al confirmar (con o sin factura), usando
    `create_caja_movimiento` (idempotente por `referencia`+`factura_id`,
    ya provisto por LibraCore).
  - Un solo medio de pago por venta por ahora (decisión del usuario) — la
    tabla `ventas_pagos` de LibraCore (pensada para multi-medio, sin
    consumidores todavía en ningún producto de la familia) queda para una
    fase posterior si hace falta partir un pago entre efectivo/tarjeta.
  - **Clientes** (`app/services/customers.py`): `Party` con extensión
    opcional `party_billing` (tabla propia con FK a `parties.id`, mismo
    patrón que `client_billing` de Gestiolibra) — opcional porque la
    mayoría de las ventas de retail son a "Consumidor Final" sin cliente
    registrado; solo hace falta si se va a facturar A/B con CUIT real.
- Verificado real: 8 tests nuevos (39 en total) + smoke end-to-end contra
  `uvicorn` real — config ARCA, cliente Responsable Inscripto facturado
  tipo A con CAE (mock de dev), venta sin cliente facturada tipo B
  "Consumidor Final", venta sin pedir factura con `factura: null`, y
  movimiento de caja confirmado en ambos casos vía `libracore.db.caja`.
- Consecuencias: VentaLibra diverge del patrón exacto de MedLibra/Gestiolibra
  en el punto de "cuándo toca caja" — es una decisión de dominio real
  (retail vs. turnos), no una inconsistencia accidental; documentado acá
  para que quede claro que es intencional si alguien compara los tres
  `billing.py` lado a lado.
- Alternativas descartadas: automatizar la factura cuando el cliente tiene
  CUIT cargado (sin flag explícito) — descartado, el usuario prefirió
  control explícito por venta; caja solo si hay factura (mismo patrón
  exacto que MedLibra/Gestiolibra) — descartado, no refleja cómo funciona
  el control de caja en un comercio real.

## ADR-008 — Renombrado TiendaLibra → VentaLibra

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: el usuario intentó registrar `tiendalibra.com.ar` (el dominio
  que la familia usa siempre para el nombre del producto — Contalibra→
  contalibra.com.ar, Restolibra→restolibra.com.ar, etc.) y no estaba
  disponible. Registró `ventalibra.com.ar` en su lugar, ya apuntando al
  servidor.
- Decisión: renombrar el producto completo a VentaLibra, no solo el
  dominio de hosting, para mantener la convención de la familia
  (nombre de producto = dominio) — se le preguntó explícitamente al
  usuario entre las dos opciones y eligió el rename completo.
- Alcance del rename: repo de GitHub (`marianocappucci/tiendalibra` →
  `marianocappucci/ventalibra`, vía `gh repo rename`), directorio local
  WSL, nombre del paquete Python (`pyproject.toml`), título de la app
  FastAPI, cookie de sesión (`tl_session` → `vl_session`, mismo patrón
  `gl_session`/`ml_session` de Gestiolibra/MedLibra), variables de entorno
  (`TIENDALIBRA_*` → `VENTALIBRA_*`), nombres de archivo de base SQLite
  por defecto (`tiendalibra.db`/`tiendalibra_libracore.db` →
  `ventalibra.db`/`ventalibra_libracore.db`), constante `EMPRESA` de
  `billing.py` (`"tienda"` → `"venta"`), y toda la documentación del
  propio repo (`README.md`/`ROADMAP.md`/`TASKS.md`/`DECISIONS.md`/
  `CHANGELOG.md`/`ARCHITECTURE.md`/`CONVENTIONS.md`) — reemplazo mecánico
  (`TIENDALIBRA`→`VENTALIBRA`, `TiendaLibra`→`VentaLibra`,
  `tiendalibra`→`ventalibra`), sin reescribir la narrativa de decisiones
  pasadas más allá del nombre del producto.
- Deliberadamente **no** se tocó el wiki `log.md` (append-only, nunca se
  reescriben entradas pasadas) — las entradas históricas siguen diciendo
  "TiendaLibra"/"RetailLibra", que es exactamente lo que se llamaba el
  producto en ese momento; la wiki registra un nuevo evento aparte para
  el rename, no reescribe el pasado.
- Verificado real: `pytest -q` 39/39 tras el rename y tras recrear el
  venv (roto por rutas absolutas del venv viejo tras mover el
  directorio), `compileall` limpio, remoto de git y `gh repo view`
  confirmando el nuevo nombre.
- Consecuencias: nada en producción se ve afectado — el dominio nunca
  había sido provisionado todavía (Fase de "provisionar dev.*.com.ar"
  sigue pendiente en ROADMAP.md), así que no hay infraestructura viva
  apuntando al nombre viejo que migrar.
- Alternativas descartadas: mantener el producto como "TiendaLibra" con
  el dominio "ventalibra.com.ar" sin relación aparente — descartado por
  el usuario, rompería la convención de la familia y generaría confusión
  permanente entre nombre de producto y dominio real.

## ADR-009 — Fase 5: planes y gating por módulo (onboarding multi-cliente)

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: para poder onboardear clientes reales hace falta un modelo de
  planes (mismo patrón que Gestiolibra/MedLibra) que gatee qué funciona
  para cada cliente según lo que paga.
- Decisión: tres planes — Básico ($20.000), Estándar ($35.000) y Premium
  ($55.000, sugerido) — con un único módulo gateable por ahora:
  `facturacion`, incluido desde Estándar. Catálogo, stock y venta/POS
  nunca se gatean (son el núcleo del producto, no un extra de plan).
  Dashboard/reportes se sumarán a Premium cuando existan.
- Implementación: `plans.py` en la raíz del repo (`PLANES`/`PLAN_LABELS`/
  `PLAN_PRECIOS`/`PLAN_MODULOS`/`aplicar_plan_en_db`, mismo shape que
  gestiolibra/medlibra) + tabla `modulos` (sqlite3 crudo, `app/db.py::
  init_modules_schema`, sembrada en `habilitado=1` para todo módulo
  conocido por defecto) + `ModuleRepository` (`app/services/modules.py`,
  `is_enabled`/`get_all`/`set_enabled`) + `require_module()` (`app/
  modules_gate.py`, dependency factory FastAPI, 403 si el módulo no está
  habilitado). `app.state.modules` es una instancia persistente creada
  una sola vez en `create_app()` — `get_module_repository()` la reusa
  (no reconstruye `ModuleRepository` por request), necesario para que
  `admin_client.app.state.modules.set_enabled(...)` en los tests mute el
  mismo objeto que ve la app.
- `confirm_sale` (`app/routers/sales.py`) chequea el módulo *antes* de
  tocar nada: si se pide `invoice=True` sin el módulo `facturacion`
  habilitado, corta con 403 antes de confirmar la venta — mismo criterio
  fail-closed que Gestiolibra/MedLibra (ver ADR-007 de este repo: caja
  siempre se registra, facturar es lo único condicionado al plan).
  Confirmar la venta sin pedir factura nunca depende del plan.
- Verificado real: 45/45 tests (39 preexistentes + 6 nuevos en
  `tests/test_modules.py`, patrón `admin_client.app.state.modules.
  set_enabled(modulo, bool)` — mismo que `gestiolibra/tests/
  test_module_gating.py`, no `aplicar_plan_en_db` contra un path de DB
  que el fixture de tests no expone), `compileall` limpio.
- Corrección (2026-07-26, ver ADR-013): esta entrada decía que
  `scripts/nuevo_cliente.py` no capturaba el plan al crear un cliente —
  **era un error de esta documentación, no un gap real**. `crear_cliente()`
  (`libracore.provisioning.nuevo_cliente`, compartido con Contalibra/
  Restolibra/Gestiolibra/MedLibra) siempre aceptó un parámetro `plan`
  (default `"basico"`, no Premium) y `main()` (el flujo interactivo)
  siempre preguntó por él explícitamente (`ask(f"Plan (...)", "basico")`)
  antes de llamar a `crear_cliente()`. `init_modules_schema` sí siembra
  todo habilitado como estado transitorio al crear la tabla, pero
  `aplicar_plan_en_db(plan)` corre inmediatamente después (dentro del
  mismo `crear_cliente()`) y lo sobreescribe según el plan real elegido
  — para cuando el onboarding termina, el plan correcto ya está aplicado.
  Ver ADR-013 para el detalle de cómo se detectó el error.

## ADR-010 — Infraestructura de deploy: Dockerfile, docker-compose, scripts y deploy keys

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: hasta ahora VentaLibra no tenía forma de deployarse — sin
  `Dockerfile` ni `docker-compose.yml` ni scripts de onboarding. Para
  levantar el primer contenedor real en el VPS hacía falta todo eso más
  el acceso SSH a las dos dependencias privadas (`libracore`,
  `libracommerce`).
- Decisión: replicar el patrón exacto de Gestiolibra/MedLibra, sin el
  stage de frontend (VentaLibra todavía no tiene uno — se suma cuando
  llegue esa fase):
  - `Dockerfile`: mismo mecanismo de `--mount=type=ssh` + alias de `Host`
    por dependencia con `IdentitiesOnly yes` (evita que GitHub autentique
    el transporte con la key equivocada del agente — bug real ya
    documentado en `gestiolibra/DECISIONS.md` ADR-014).
  - `docker-compose.yml`: contenedor `ventalibra-dev`, puerto `8081`
    (siguiente libre después de `medlibra-dev` en `8077`; confirmado
    contra `docker ps` real en el VPS, no asumido), red `stack-net`
    externa, healthcheck sobre `/health`.
  - `scripts/nuevo_cliente.py`/`panel_admin.py`/`npm_api.py`/
    `npm_setup.py`: wrappers delgados sobre `libracore.provisioning` /
    `libracore.npm_api`, `base_port=8082` (siguiente libre después de
    `medlibra`'s `8078`).
  - `app/asgi.py`: puentea el contrato `DATA_DIR`/`ADMIN_USER`/
    `ADMIN_PASSWORD` que escribe `libracore.provisioning` para clientes
    reales, sin romper el arranque explícito por env vars que usa el
    `docker-compose.yml` de dev (`VENTALIBRA_DB_PATH`/
    `VENTALIBRA_ADMIN_*`).
  - Deploy keys SSH nuevas (convención de `CLAUDE.md`/`AGENTS.md` del
    wiki, sin PAT embebido): `id_ed25519_libracommerce` (solo lectura,
    primera vez que un producto depende de LibraCommerce — no se puede
    reusar la de LibraCore, GitHub no permite compartir una deploy key
    entre repos) y `id_ed25519_ventalibra` (read-write, propia del repo,
    para el `git pull` de deploy). Ambas generadas en el VPS y cargadas
    en el ssh-agent persistente compartido (`agent-multi-libra.sock`,
    ya tenía las de LibraCore/LibraGenda); alias `github-ventalibra`
    agregado a `~/.ssh/config` del VPS **antes** del bloque genérico
    `Host *` (el orden importa, ver incidente documentado en
    `CLAUDE.md`).
- Verificado real en el VPS (no solo localmente): clone vía
  `github-ventalibra`, `docker compose build` con
  `LIBRACORE_SSH_KEY=~/.ssh/agent-multi-libra.sock` resolviendo
  `libracommerce`/`libracore` por SSH sin exponer ninguna clave privada
  en capas de la imagen, `docker compose up -d` con contenedor healthy,
  `GET /health` → 200, login real contra `/auth/login` con las
  credenciales default de dev (`admin`/`admin`, vía `ENV=development`
  en `ensure_default_admin`) → 200.
- Bloqueado, resuelto el mismo día: `ventalibra.com.ar` tenía la
  delegación DNS mal configurada — los nameservers delegados
  (`200.58.112.193`/`.101`) devolvían `REFUSED` ("lame delegation",
  confirmado vía DNS-over-HTTPS contra `dns.google`) en vez de responder
  por la zona. El usuario lo corrigió del lado del proveedor de DNS;
  reverificado (`ventalibra.com.ar`/`dev.ventalibra.com.ar` →
  `149.50.136.218`, IP real del VPS) antes de seguir.
- **NPM + SSL provisionados para `dev.ventalibra.com.ar`**: proxy host
  id `31`, `forward_host=ventalibra-dev` (nombre del contenedor en su
  puerto interno `8000` — mismo patrón que `contalibra-dev`/
  `gestiolibra-dev`/`restolibra-dev`, todos en la red compartida
  `stack-net` donde NPM puede resolver por nombre de contenedor; **no**
  el patrón `172.18.0.1:<puerto publicado>` que quedó en
  `dev.medlibra.com.ar` como inconsistencia histórica sin corregir).
  Config de NPM (`scripts/.npm_config.json`, mismas credenciales que
  Gestiolibra/MedLibra/Restolibra — mismo NPM del VPS) copiada de
  `gestiolibra/scripts/.npm_config.json` a nivel de archivo, sin leer ni
  manejar el valor de `npm_password` en ningún momento. Venv dedicado
  `.venv-scripts` (mismo patrón que los demás productos, usado por
  `panel_admin.py`/`nuevo_cliente.py`) creado en el checkout del VPS
  instalando `libracore`/`libracommerce` vía los alias SSH
  `github-libracore`/`github-libracommerce` del **host** (no solo los
  horneados en la imagen Docker — hacía falta un alias aparte para
  `pip install` fuera de contenedor).
- Verificado real: `GET https://dev.ventalibra.com.ar/health` → 200 con
  certificado válido, desde fuera del VPS.

## ADR-011 — Primer cliente real onboardeado vía `scripts/nuevo_cliente.py`

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: con DNS, deploy keys e infraestructura resueltos (ADR-010),
  correspondía onboardear el primer cliente real (no el contenedor
  `-dev` manual, que solo sirve para verificar la infraestructura) para
  probar el flujo completo de `crear_cliente()` (`libracore.provisioning
  .nuevo_cliente`, compartido con Contalibra/Restolibra/Gestiolibra/
  MedLibra) de punta a punta por primera vez en este repo.
- **Bug real encontrado y corregido, no específico de VentaLibra**:
  `crear_cliente()` → `build_image()` corre `docker build -t
  {image_name} .` **sin** `--ssh`, así que si la imagen todavía no
  existe con el tag exacto que espera `configure(image_name=...)`
  (`ventalibra:latest`), el build falla al clonar `libracommerce`/
  `libracore` por SSH (`Load key .../id_libracommerce.pub: error in
  libcrypto` — intenta usar la public key horneada como si fuera la
  identidad real, sin ningún agente forwardeado). El `docker-compose.yml`
  de dev (ADR-010) sí pasa `--ssh` correctamente, pero `docker compose
  build` nombra la imagen `ventalibra-ventalibra-dev:latest`, **no**
  `ventalibra:latest` — nunca coincide con lo que `image_exists()`
  busca. Confirmado que Gestiolibra/MedLibra tienen exactamente el mismo
  problema latente, solo que invisible: ambos ya tienen `gestiolibra:
  latest`/`medlibra:latest` construidos aparte (`docker images` en el
  VPS lo confirma), separado de sus imágenes `-dev`. Fix aplicado (mismo
  patrón, no un cambio a `libracore`): `docker build -t ventalibra:latest
  --ssh default=$SSH_AUTH_SOCK .` corrido una vez a mano en el VPS con
  el agente compartido — deja `image_exists()` en `True` para siempre,
  así `crear_cliente()` nunca vuelve a intentar `build_image()` sin
  `--ssh`. No se tocó `libracore.provisioning` (afecta a toda la
  familia, decisión fuera de alcance de esta ronda).
- Cliente creado: `prueba` (`Cliente de Prueba`, plan **Premium** — mismo
  criterio que `gestiolibra-prueba`/`medlibra-prueba`), puerto `8082`
  (siguiente libre tras `8081` del `-dev`), dominio
  `prueba.ventalibra.com.ar` (DNS wildcard de `ventalibra.com.ar` ya
  cubre cualquier subdominio, confirmado antes de asumirlo). Proxy NPM
  con SSL creado automáticamente por `crear_cliente()` (`forward_host
  =172.18.0.1:8082` — patrón gateway+puerto-publicado-al-host, distinto
  del `container-name:8000` usado para `dev.ventalibra.com.ar` en
  ADR-010; ambos patrones coexisten en la familia según si el proxy lo
  arma el script de onboarding automatizado o se arma a mano para un
  `-dev`).
- Verificado real: contenedor `ventalibra-prueba` healthy, `GET
  https://prueba.ventalibra.com.ar/health` → 200, login real contra
  `/auth/login` con las credenciales generadas por el script (contraseña
  aleatoria de `secrets.token_urlsafe`, persistida en
  `clientes/prueba/cliente.json` en el VPS — no se guarda en ningún otro
  lado). Plan `premium` aplicado correctamente vía `aplicar_plan_en_db`.
- No corregido a propósito (no es un bug de esta sesión, es un
  comportamiento heredado y consistente con toda la familia): el nombre
  de display del admin queda siempre "Administrador", ignorando
  `ADMIN_NOMBRE`/`admin_nombre` — confirmado que
  `gestiolibra/app/services/users.py::ensure_default_admin` tiene
  exactamente el mismo hardcodeo. No se toca sin decisión explícita, ya
  que cambiarlo solo acá rompería la consistencia entre productos.

## ADR-012 — Conectar Fase 4 de LibraCommerce: códigos, listas de precio y variantes

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: las tres piezas de Fase 4 (`item_codes`/`price_lists`+
  `item_prices`/`item_variants`) se construyeron enteramente del lado de
  LibraCommerce, sin ningún consumidor todavía — el usuario pidió
  conectarlas a VentaLibra para que dejen de ser código muerto.
- Pin de `libracommerce` actualizado a `v0.1.3` (tag cortado sobre
  `develop`@`81ab280`, incluye las tres features). Necesitó
  `pip install --force-reinstall` porque el número de versión propio de
  LibraCommerce (`0.1.0` en su `pyproject.toml`) nunca cambia entre tags
  — pip ve la misma versión "ya satisfecha" y no vuelve a clonar el repo
  aunque el tag apuntado en la URL haya cambiado. Mismo cuidado a tener
  en cuenta la próxima vez que se bump-ee este pin.
- **Códigos de barra**: `CatalogService.add_code`/`list_codes`/
  `find_by_code`. Router: `POST`/`GET /catalog/items/{id}/codes` +
  `GET /catalog/items/scan?code=...` (resuelve el item completo, pensado
  para el caso de uso real de escanear en el POS). La ruta `scan` se
  registró **antes** que `/items/{item_id}` en el archivo a propósito:
  ambas tienen la misma forma de dos segmentos, y FastAPI/Starlette
  matchea por orden de registro — si `{item_id}` fuera primero, "scan"
  caería ahí y fallaría al intentar convertirlo a `int` en vez de llegar
  al endpoint real.
- **Listas de precio**: nuevo servicio/router `pricing` —
  `POST /pricing/lists`, `POST /pricing/items/{id}/prices`,
  `GET /pricing/items/{id}/resolve` (expone `resolve_price` de
  LibraCommerce tal cual). `SaleService.add_item` ahora resuelve el
  precio en este orden: `unit_price` explícito (si el caller lo manda) →
  `resolve_price()` (si hay un precio configurado, en la lista pedida o
  la default) → `default_sale_price` del catálogo como último fallback
  — nunca rompe el comportamiento anterior para catálogos sin listas de
  precio configuradas.
- **Variantes**: `CatalogService.add_variant`/`list_variants`/
  `get_variant`. `SaleService.add_item` acepta `variant_id` opcional y
  **valida que pertenezca al item** (`variant.item_id == item_id`,
  `KeyError`→422 si no) antes de crear la línea — el mismatch nunca
  llega a persistirse. `StockService.adjust`/`current_stock`/`movements`
  ganaron `variant_id` opcional, delegando en el filtro exacto que ya
  expone `SqliteCommerceRepository`.
- **Verificado real de punta a punta contra `uvicorn`** (no solo
  `TestClient`): alta de código → escaneo resuelve el item → alta de
  variante con atributos → lista de precio default + precio por
  item/lista → `resolve_price` devuelve el precio configurado (4500),
  no el `default_sale_price` del catálogo (5000) → ajuste de stock por
  variante → venta de esa variante usa el precio resuelto (verificado en
  el JSON de la respuesta) y al confirmar descuenta el stock de **esa**
  variante puntual (10 → 8), no el del item agregado.
- 17 tests nuevos (**62 en total**): 6 de catálogo (códigos, scan,
  duplicado, variantes, SKU duplicado), 6 de pricing (listas, segundo
  default rechazado, precios por item, ventana de vigencia inválida,
  resolución sin precio configurado, resolución vía lista default), 4
  de ventas (venta de variante mueve el stock correcto, variante
  desconocida rechazada, precio resuelto vs. default), 1 de stock (stock
  independiente por variante).

## ADR-013 — Corrección: la captura de plan en el onboarding ya existía (no era un pendiente real)

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: quedaba anotado en ROADMAP.md/TASKS.md/DECISIONS.md (ADR-009)
  que `scripts/nuevo_cliente.py` "no captura el plan elegido al crear un
  cliente — todo cliente nuevo arranca en Premium por default". El
  usuario eligió atacar este pendiente; antes de tocar código se
  releyó `libracore.provisioning.nuevo_cliente` para confirmarlo.
- Hallazgo: **la nota era incorrecta**, no un gap real. `crear_cliente()`
  siempre tuvo un parámetro `plan: str = "basico"` (default `"basico"`,
  no Premium — otro dato erróneo de la nota original), y `main()` (el
  modo interactivo) siempre preguntó explícitamente `Plan (basico/
  estandar/premium)` antes de confirmar el alta. El cliente de prueba
  `prueba` (ver ADR-011) ya se había dado de alta con `plan="premium"`
  pasado explícitamente — la propia sesión anterior ya había usado esta
  capacidad sin darse cuenta de que contradecía la nota escrita.
- Origen probable del error: al onboardear `prueba` se llamó a
  `crear_cliente()` directamente vía un script Python (no el flujo
  interactivo `main()`), pasando `plan="premium"` a mano — se generalizó
  incorrectamente esa elección manual como "el script no soporta elegir
  plan", cuando en realidad ambos caminos (interactivo y programático)
  ya lo soportaban.
- Gap real distinto, encontrado de paso (no confundir con el anterior):
  **no existe ningún comando para cambiar el plan de un cliente ya
  onboardeado** — `libracore.provisioning.panel_admin` tiene comandos
  para listar/iniciar/parar/backup/activar/pausar/suspender/eliminar,
  pero ninguno de tipo `cambiar-plan`. Esto es transversal a toda la
  familia (mismo módulo compartido con Contalibra/Restolibra/Gestiolibra/
  MedLibra), no específico de VentaLibra — queda documentado como
  pendiente real, sin atacar en esta ronda (fuera del pedido del
  usuario, y tocaría `libracore` compartido, no solo este repo).
- Sin cambios de código en este repo — corrección puramente documental.
  Ver también el ADR-009 corregido arriba.

## ADR-014 — Frontend: SPA en React+Vite+Tailwind+shadcn/ui, MVP de login + POS + catálogo

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: quedaban dos pendientes de tamaño muy distinto; el usuario
  eligió "captura de plan" primero (ver ADR-013), y a continuación pidió
  arrancar el frontend. Se consultaron dos decisiones antes de codificar:
  stack (Tailwind+shadcn/ui desde el día uno vs. MVP simple con CSS
  propio como arrancó Gestiolibra) y alcance del primer corte (login+POS
  vs. +catálogo vs. back office completo).
- Decisión — stack: **Tailwind+shadcn/ui desde el día uno**, el estándar
  actual de la familia (ver `CLAUDE.md`/`AGENTS.md` del wiki, referencia
  Gestiolibra `DECISIONS.md` ADR-019/025/026) — evita el camino que hizo
  Gestiolibra (MVP con CSS propio, rediseño completo después). React 19 +
  TypeScript + Vite + Tailwind v4 (`@tailwindcss/vite`, sin
  `tailwind.config.js` separado) + componentes shadcn/ui (código fuente
  propio en `frontend/src/components/ui/`, copiados y adaptados de
  Gestiolibra — son primitivos genéricos sin lógica de negocio, no una
  dependencia de npm) + TanStack Table + React Hook Form + Zod (las
  últimas dos instaladas y listas, `DataTable` ya wireado con sorting,
  pero esta ronda no tuvo un formulario que necesitara Zod todavía).
- Decisión — alcance del MVP: **login + POS de venta + catálogo**
  (alta de items/códigos/variantes) — se dejó afuera el resto del back
  office (compras, proveedores, clientes, config ARCA, usuarios), que se
  sigue manejando por API directa. La razón de sumar catálogo al MVP
  (no solo login+POS, que hubiera sido el mínimo estilo Gestiolibra
  original) fue explícita: sin eso, cargar el catálogo inicial dependía
  de curl/Postman.
- Decisión — auth y same-origin: mismo patrón que Gestiolibra — cookie
  de sesión `vl_session`, proxy de Vite en dev (`vite.config.ts`, lista
  de prefijos de la API real de este repo: `/auth`, `/catalog`,
  `/pricing`, `/locations`, `/stock`, `/sales`, `/suppliers`,
  `/purchase-orders`, `/purchase-receipts`, `/customers`, `/users`,
  `/config`, `/health`), build servido desde el mismo proceso FastAPI en
  producción (`app/asgi.py`: mount `/assets` + catch-all `GET
  /{full_path:path}` → `index.html`, registrado *después* de que
  `create_app()` monta todos los routers de la API, para que estos
  tengan prioridad).
- **POS** (`src/pages/Pos.tsx`): buscar por nombre o escanear un código
  de barras (`GET /catalog/items/scan`) — si el código no resuelve, cae
  a buscar por nombre (`GET /catalog/items?search=`) y muestra una
  lista para elegir. Si el item tiene variantes, exige elegir una antes
  de agregar (`GET /catalog/items/{id}/variants`). Crea la venta
  borrador recién al agregar la primera línea (`POST /sales` lazy, no al
  entrar a la página). Confirmar pide sucursal/depósito + medio de pago
  (lista fija: efectivo/débito/crédito/transferencia/Mercado Pago, sin
  restricción del backend) + checkbox opcional de factura.
- **Catálogo** (`src/pages/Catalogo.tsx`): alta rápida de unidades
  (con toggle "se vende por fracción" para productos pesables — ya
  soportado desde Fase 1, ver `wiki/entities/libracommerce.md`), alta de
  items, tabla con `DataTable`/TanStack Table, y un `Dialog` por item
  ("Gestionar") con dos secciones para dar de alta códigos de barra
  (con selector de `code_type`) y variantes (SKU + nombre).
- Docker: `Dockerfile` suma un stage `frontend-build` (`node:20-slim`,
  mismo patrón que Gestiolibra) — el resultado se hornea en
  `/opt/frontend-dist`, **fuera** de `/app`, porque el `docker-compose.yml`
  de dev bind-montea `./:/app` entero para el `--reload` de Python, lo
  que taparía cualquier build copiado dentro de `/app` con el checkout
  del host (sin `frontend/dist`, gitignoreado). CI **no** se tocó — ni
  siquiera Gestiolibra (la referencia) compila el frontend en su propio
  CI todavía, así que no se introdujo esa inconsistencia de pasada.
- **Verificado real de punta a punta**, no solo `npm run build`: el
  proxy de Vite (`localhost:5173`) quedó bloqueado por el chequeo de
  host del entorno de verificación de esta sesión (no un bug de la app:
  `localhost:8000`, el backend plano sin ese chequeo, sí fue alcanzable
  y sirvió el HTML correctamente) — se verificó entonces contra un
  **build de producción real** servido por `uvicorn app.asgi:app`, que
  es exactamente el mismo artefacto que corre en el VPS. Flujo probado
  en el navegador real: login → crear unidad → crear item (Remera,
  $5.000) → agregar código de barras → agregar variante (M/Azul) →
  volver al POS → escanear ese código → elegir la variante → agregar a
  la venta (línea muestra "Remera (M / Azul)") → confirmar (sin
  factura) → verificado por API que el stock de esa variante puntual
  bajó a -1 (sin stock previo cargado, comportamiento esperado).
- `npm run build` (`tsc -b && vite build`) sin errores de tipos.
  Suite de tests del backend sin cambios (62/62), `compileall` limpio.
- Pendiente (fuera de esta ronda): resto del back office
  (compras/proveedores/clientes/config ARCA/usuarios/sucursales) y
  reportes — se suman cuando el usuario los priorice, un corte a la vez,
  mismo criterio que el resto de Fase 5.

## ADR-015 — Frontend: resto del back office (sucursales, proveedores, clientes, compras, usuarios, config ARCA)

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: con el MVP del frontend cerrado (ADR-014), el usuario pidió
  seguir con el resto del back office en el mismo frontend.
- **Gap real encontrado antes de codificar Compras**: no existía forma
  de *listar* órdenes de compra ni recepciones — `PurchasingService`/
  `SqliteCommerceRepository` solo tenían `get_*_by_id`. Se agregó
  `list_purchase_orders()`/`list_purchase_receipts()` en LibraCommerce
  (reusando `_purchase_order_from_row()`/`_purchase_receipt_from_row()`
  extraídos de los `get_*` existentes), se cortó `v0.1.4` y se actualizó
  el pin. `GET /purchase-orders`/`GET /purchase-receipts` nuevos en este
  repo (sin ambigüedad de rutas con `/purchase-orders/{id}`: distinta
  profundidad de path, a diferencia del caso `/items/scan` vs
  `/items/{id}` de ADR-012).
- **Bug real encontrado y corregido** (no introducido en esta ronda,
  preexistente desde Fase 2, pero invisible hasta que una UI lista
  ambas cosas juntas): `SupplierService.list_all()`/
  `CustomerService.list_all()` consultaban *todas* las `parties` activas
  sin filtrar por rol — un cliente aparecía mezclado en la lista de
  proveedores y viceversa. La causa raíz: `Party.party_type` es
  persona/organización, un eje totalmente distinto al de
  cliente/proveedor (un proveedor puede ser persona, un cliente puede
  ser organización), y el rol se documentaba como "contextual" sin
  ninguna columna que lo persista. Fix: tabla local `party_roles`
  (`party_id`, `role`, PK compuesta para no cerrar la puerta a que una
  misma party tenga los dos roles a la vez más adelante) — mismo patrón
  exacto que `party_billing` (extensión propia de este repo con FK a
  `parties.id`, sin tocar el esquema genérico de LibraCommerce).
  `SupplierService.create()`/`CustomerService.create()` ahora insertan
  el rol correspondiente; `list_all()` de ambos hace `JOIN` contra
  `party_roles` filtrando por rol. 2 tests nuevos confirmando que las
  listas no se cruzan.
- **Páginas nuevas**:
  - Sucursales/Proveedores/Clientes: alta + listado únicamente — esos
    tres routers no tienen `PUT`/`DELETE` en el backend, así que no hay
    edición/baja en la UI tampoco (no se agregaron endpoints nuevos para
    esto, fuera de lo pedido).
  - Usuarios: CRUD completo (ya existía `PUT`/`DELETE` en el backend),
    admin-only.
  - Config ARCA: formulario simple `GET`/`PUT`, admin-only.
  - Compras: dos paneles (órdenes de compra, recepciones), cada uno con
    lista + panel de detalle para la orden/recepción seleccionada
    (crear, agregar líneas, y en recepciones también confirmar con
    depósito de destino).
- `App.tsx`/`Layout.tsx`: 6 rutas nuevas. Nav items de Usuarios/Config
  ARCA marcados `adminOnly` (mismo patrón que Gestiolibra) — ocultos del
  sidebar para `staff` y la ruta redirige a `/pos` si se navega directo
  (sin depender solo del 403 del backend para la UX).
- **Bug propio encontrado y corregido durante la verificación real**
  (no un bug de LibraCommerce ni del backend de este repo):
  `Compras.tsx` usaba `!selected.is_fully_received` para decidir si
  mostrar el formulario de alta de líneas en una orden — pero
  `is_fully_received()` es `all(item.pending_quantity <= 0 for item in
  self.items)`, que da **vacuamente `true`** sobre una colección vacía.
  Resultado: una orden recién creada (sin líneas todavía) ocultaba el
  formulario justo cuando hacía falta. Corregido para mirar `status`
  (`draft`/`sent` permiten agregar líneas), el mismo criterio que ya
  valida `PurchasingService.add_order_item()` del lado del backend —
  encontrado recién al probar el flujo completo en el navegador real,
  no por revisión de código.
- **Verificado real de punta a punta contra un build de producción**
  servido por `uvicorn` (mismo método que ADR-014, no solo `npm run
  build`): las 6 páginas nuevas navegadas y ejercitadas, incluido un
  flujo completo de compras (crear recepción → agregar línea → confirmar
  → stock y `default_cost` actualizados, verificado por API) y de
  órdenes (crear orden → agregar línea, verificado que la línea con
  cantidad pedida 20 aparece correctamente tras el fix del bug de
  arriba). Nota metodológica: los selects de Radix/shadcn quedaron en un
  estado de overlay "pegado" al reusar la misma pestaña para múltiples
  interacciones seguidas dentro de la misma sesión de verificación — se
  resolvió recargando la página entre bloques de prueba, no es un bug
  de la app.
- `npm run build` sin errores de tipos. Suite de tests del backend:
  66/66 (2 de `party_roles`, 2 de `list_purchase_orders`/
  `list_purchase_receipts`), `compileall` limpio.
- Pendiente (fuera de esta ronda): reportes de ventas/caja/stock.

## ADR-016 — Reportes de ventas, caja y stock (cierra Fase 5)

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: único pendiente que quedaba de Fase 5 tras el back office
  completo (ADR-015). Mismo patrón que el dashboard de Gestiolibra/
  MedLibra (`app/services/dashboard.py` de esos repos): lectura pura de
  agregación sobre datos que ya se generan, sin tabla ni estado propio.
- **`/reports/sales`**: cuenta y suma `sales` con `status='confirmed'`
  en un rango de fechas, agrupa por día, y arma un top-10 de items más
  vendidos (`sale_items` con `kind='product'`). Decisión técnica: filtrar
  por el **prefijo `YYYY-MM-DD` de `confirmed_at` como string**
  (`substr(confirmed_at, 1, 10) BETWEEN ? AND ?`) en vez de las funciones
  `date()`/`datetime()` de SQLite — `confirmed_at` se guarda con offset
  de timezone (`...+00:00`, vía `datetime.now(timezone.utc).isoformat()`
  en `libracommerce.usecases.sales.confirm_sale`), y comparar el prefijo
  ISO como string evita cualquier ambigüedad de cómo SQLite parsea ese
  formato — un string ISO bien formado siempre compara/ordena
  correctamente de forma lexicográfica.
- **`/reports/caja`**: delega enteramente en
  `libracore.db.caja.get_caja_resumen(desde, hasta)` — la misma conexión
  global que ya configura `app/services/billing.py::configure()` al
  arrancar la app, sin wiring adicional. Mismo patrón exacto que usa el
  dashboard de Gestiolibra/MedLibra para su bloque de facturación/caja.
- **`/reports/stock`**: stock actual por item = `SUM(quantity_delta)` de
  `stock_movements` agrupado por item (mismo cálculo que ya usa
  `current_stock()` de `SqliteCommerceRepository`, pero agregado por
  todos los depósitos en vez de uno solo — a propósito, un reporte
  gerencial no necesita el desglose por depósito todavía). Lista
  `low_stock` con un threshold configurable (default `0`) para flaggear
  items sin stock.
- Gating: **admin-only**, sin módulo de plan asociado — mismo criterio
  que el dashboard de Gestiolibra (`adminOnly: true` en el nav, sin
  gatear por `require_module`, a diferencia de facturación que sí
  depende del plan).
- **Verificado real de punta a punta contra un build de producción**:
  venta confirmada de $4.000 con 2 unidades de "Yerba 1kg" → el reporte
  de ventas la cuenta (`total_ventas=1`, `total_facturado=4000`) y la
  lista en `top_items`; el reporte de caja refleja el ingreso
  (`ingresos=4000`, `saldo_periodo=4000`); el reporte de stock muestra
  8 unidades restantes (10 cargadas − 2 vendidas) y marca un segundo
  item sin stock como `low_stock`.
- 8 tests nuevos (**74 en total**), incluido que un usuario `staff`
  recibe 403 al intentar acceder. `npm run build` sin errores,
  `compileall` limpio.
- **Con esto, Fase 5 queda completa**: planes/gating, infraestructura
  de deploy, dominio/SSL, frontend completo (POS/catálogo/back
  office/reportes). Próximo hito de VentaLibra queda fuera de Fase 5 —
  a definir cuando el usuario lo priorice (ej. onboardear el primer
  cliente pagante real, Fase 4 residual como `item_prices.variant_id`,
  u otro producto de la familia).

## ADR-017 — Incidente `dev.ventalibra.com.ar` caído + mecanismo real de migraciones de esquema en LibraCommerce

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: reportado por el usuario ("si entro a dev.ventalibra.com.ar
  no me deja entrar") inmediatamente después de cerrar Fase 5 (ADR-016).

### Causa inmediata

`dev.ventalibra.com.ar/health` respondía 200 (API viva) pero `/`
devolvía 404 — el contenedor `-dev` del VPS corría código viejo
(`git log -1` mostraba el commit de la mañana, `42a4695`, sin ninguno de
los cambios de Fase 4/frontend/back office/reportes del día), es decir
sin la ruta catch-all del SPA que agregó ADR-014. `git pull` en el VPS
(`42a4695` → `89fe287`, 77 archivos) y rebuild del contenedor
solucionaba el síntoma visible — pero el rebuild expuso un problema más
profundo.

### Causa raíz

Al recrear el contenedor con el código nuevo, crasheó en el arranque:
`sqlite3.OperationalError: no such column: variant_id`. Motivo:
`libracommerce/db/schema.py::init_schema()` usa `CREATE TABLE IF NOT
EXISTS` para todo el esquema — que es un **no-op silencioso** si la
tabla ya existe en el archivo. Cuando Fase 4 agregó `variant_id` a
`stock_movements` y `sale_items` (columnas que no existían antes), esa
sentencia nunca las agrega a una base **ya persistida** creada con el
esquema anterior — solo a una base nueva. Invisible en todos los tests
(siempre arrancan de `:memory:`/temporal fresca) pero rompe cualquier
despliegue real apenas se suma una columna a una tabla existente.
Bug latente desde que se mergeó Fase 4 (item_variants), recién
manifestado ahora al reiniciar `-dev` con datos persistidos de antes de
esa fase.

Se preguntó al usuario si documentar el riesgo nomás o resolverlo de
una — **decisión explícita: "Atacarlo ahora"**.

### Fix inmediato (solo `-dev`, datos descartables de verificación)

`docker compose down && rm -f dev-data/*.db && SECRET_KEY=... docker
compose up -d` — recrea `-dev` desde cero, sin problema porque esos
datos son solo de prueba, nunca de un cliente real. Verificado
funcionando (`/` → 200, login admin/admin → 200).

### Fix de fondo: mecanismo real de migraciones en LibraCommerce

Nuevo módulo `libracommerce/db/migrations.py`: lista numerada de
migraciones idempotentes (`_MIGRATIONS`), cada una verificando
`PRAGMA table_info()` antes de tocar nada, además trackeadas en tabla
`schema_migrations` (`version`/`name`/`applied_at`). `run_migrations(conn)`
se invoca al final de `init_schema()` — no-op tanto en una base fresca
(ya trae las columnas nuevas desde el `CREATE TABLE`) como en una base
ya migrada (idempotente), y aplica el fix real en una base vieja
genuina.

- `stock_movements.variant_id`: `ALTER TABLE ADD COLUMN` simple (sin
  CHECK multi-columna).
- `sale_items.variant_id`: requirió el rebuild de 12 pasos recomendado
  por la documentación de SQLite (rename → create con el esquema
  completo deseado → `INSERT INTO ... SELECT` copiando datos con
  `variant_id=NULL` → drop) porque el CHECK
  `(variant_id IS NULL OR item_id IS NOT NULL)` referencia dos columnas
  y SQLite no permite agregar un CHECK así vía `ADD COLUMN`.
- **Bug secundario encontrado en el camino**: el `executescript()` del
  esquema tenía `CREATE INDEX ... ON stock_movements(item_id,
  variant_id, location_id)` como sentencia standalone (no parte del
  `CREATE TABLE`) — eso también fallaba contra una base vieja sin
  `variant_id`, y además **antes** de que las migraciones tuvieran
  oportunidad de correr (crasheaba el `executescript()` entero). Se
  movió la creación de ese índice a la migración misma.
- 8 tests nuevos (`tests/test_migrations.py`), construyendo a mano un
  esquema real pre-Fase-4 con datos insertados, verificando: no
  crashea, datos preservados exactamente, columna usable, ambos CHECK
  siguen validando, idempotencia en doble llamada, y que una base
  fresca también registra la migración como aplicada. Suite completa:
  89/89. LibraCommerce `v0.1.5`, VentaLibra pin bumpeado a esa versión.

### Verificación contra datos reales (no solo sintética)

Además de los 8 tests nuevos y de redeployar `-dev` (con datos ya
reseteados, no probaba el camino real de migración), se decidió
explícitamente extender la verificación al cliente `prueba` — único
contenedor con una base persistida genuinamente anterior a Fase 4.
**Decisión explícita del usuario: "Sí, actualizalo".**

1. Backup previo de ambas bases de `prueba`
   (`/root/backups_incidente_2026-07-26/prueba_ventalibra{,_libracore}.db.bak`)
   antes de tocar nada — precaución, no hizo falta restaurarlo.
2. Rebuild de la imagen base `ventalibra:latest` (`docker build --ssh
   default=$SSH_AUTH_SOCK`, no `docker compose build` — esa imagen la
   usan los contenedores de clientes, no `-dev`).
3. `docker compose up -d` en `clientes/prueba/` — contenedor arrancó
   **healthy** sin crash.
4. Verificado desde dentro del contenedor: `schema_migrations` con la
   fila `(1, 'add_variant_id_to_stock_movements_and_sale_items',
   '2026-07-26 16:54:39')`, columna `variant_id` presente en
   `sale_items` y `stock_movements`. `/health` 200, `/` sirve el SPA,
   login admin funcionando (200).
5. `prueba` no tenía filas en `sale_items`/`stock_movements` (cliente de
   prueba sin transacciones reales cargadas) — la migración no tuvo
   datos que preservar en este caso puntual, pero corrió sobre el
   esquema real sin fallar, que era el objetivo de la verificación.
6. `ventalibra-prueba` estuvo `Up (healthy)` corriendo la imagen vieja
   sin interrupción durante todo el incidente — ningún impacto al
   cliente mientras se diagnosticaba y arreglaba.

### Lecciones

- **Riesgo transversal**: el mismo patrón (`CREATE TABLE IF NOT
  EXISTS` sin migraciones) puede repetirse en cualquier otro producto
  de la familia que use LibraCommerce como motor compartido — el fix
  vive en LibraCommerce, así que cualquier producto pineado a `>=
  v0.1.5` ya lo tiene.
- LibraCommerce todavía no tiene `DECISIONS.md`/`ROADMAP.md` propios
  (solo `README.md`) — este incidente quedó documentado del lado
  LibraCommerce solo en mensajes de commit, no en un ADR propio de ese
  repo. Pendiente si se decide adoptar el estándar híbrido ahí también.

## ADR-018 — Endpoint `POST /auth/verify` para el login de `/docs/` de ventalibra_web

- Estado: aceptada
- Fecha: 2026-07-26
- Contexto: se construyó `ventalibra_web`, la landing de marketing del
  producto, con documentación técnica en `/docs/` gateada por login —
  mismo patrón que ya usan Contalibra/Restolibra/Gestiolibra/MedLibra:
  la landing no guarda usuarios propios, valida en tiempo real contra
  la instancia real del cliente vía un endpoint interno protegido por
  un secreto compartido (`DOCS_AUTH_SECRET`). Ese endpoint no existía
  todavía en VentaLibra.
- Decisión: mismo diseño exacto que Gestiolibra/MedLibra. `POST
  /auth/verify` en `app/routers/auth.py`, junto a
  `/login`/`/logout`/`/me`. Recibe `username`/`password`, exige el
  header `X-Internal-Auth` comparado con `hmac.compare_digest()`
  contra `DOCS_AUTH_SECRET` (leído del entorno en cada request) y
  responde `{"valid": bool}` reusando
  `UserRepository.check_credentials()`, sin crear cookie de sesión.
  Falla cerrado (401) si el secreto no está configurado.
- Consecuencias: 5 tests nuevos (`tests/test_auth_verify.py`). Suite
  completa verificada en verde salvo el flake ya documentado del reloj
  de WSL2 (un test distinto en cada corrida, no relacionado con este
  cambio). Sin cambios de frontend ni de ningún otro endpoint. Detalle
  del lado de la landing en `ventalibra_web` (`auth/app.py`).
