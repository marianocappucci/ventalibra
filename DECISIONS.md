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

- Estado: aceptada; **el esquema de tres planes y el módulo `facturacion` «desde Estándar» quedaron reemplazados por
  ADR-048** (dos planes: Básico y Premium). El mecanismo (tabla `modulos`, `require_module`) sigue vigente.
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
  vendidos (`sale_items` con `kind='product'`).

  > 🔴 **Corregido el 2026-08-24.** Acá decía: filtrar por el prefijo
  > `YYYY-MM-DD` de `confirmed_at` como string
  > (`substr(confirmed_at, 1, 10) BETWEEN ? AND ?`), porque `confirmed_at` se
  > guarda con offset (`...+00:00`, vía `datetime.now(timezone.utc)`) y comparar
  > el prefijo ISO como string evita la ambigüedad de cómo SQLite parsea ese
  > formato.
  >
  > **La mitad de ese razonamiento seguía siendo cierta y la otra mitad era el
  > defecto.** Es verdad que un ISO bien formado compara y ordena
  > lexicográficamente. Pero el prefijo de un timestamp guardado en UTC es la
  > fecha **UTC**, y el rango que llega por querystring son fechas **locales**:
  > entre las 21:00 y las 24:00 de Argentina son dos días distintos, así que una
  > venta confirmada a las 22:00 del 14 quedaba contada en el 15 — **no aparecía
  > en el reporte del día en que se vendió**, justo en la franja de cierre.

  Decisión vigente: **se convierte el rango, no la columna.** El día local
  `[desde, hasta]` se traduce en Python a una ventana **semiabierta** de
  instantes UTC —`[desde 03:00, hasta+1d 03:00)`— y el SQL sólo compara
  `confirmed_at >= ? AND confirmed_at < ?`. Eso conserva la idea buena (el motor
  no parsea ninguna fecha; alcanza la comparación lexicográfica) y arregla el
  huso. El agrupado por día se arma en Python, porque el día es el **local**.

  Se convierte del lado de Python y no del motor **a propósito**: la suite corre
  contra los dos —SQLite en el primer paso del CI y PostgreSQL en el segundo—, y
  una conversión en SQL habría que escribirla dos veces. Cubierto por
  `test_una_venta_del_cierre_cuenta_en_el_dia_que_se_vendio`, que fija el
  instante guardado en vez de depender de la hora de la corrida, con su control
  positivo (`..._del_mediodia_no_se_mueve_de_dia`) y su control negativo (que la
  venta **no** quede contada también en el día UTC).
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

## ADR-019 — Balanza de mostrador: formato configurable, parser en LibraCommerce

- Estado: aceptada
- Fecha: 2026-07-28
- Contexto: fiambrería y verdulería son el corazón de una despensa, y sin
  balanza el producto queda afuera del rubro (ver
  `wiki/analyses/ventalibra-gaps-despensa.md`). Una balanza de mostrador
  imprime un EAN que **no identifica un producto**: identifica un producto
  y cuánto se pesó de él, con la forma `prefijo | código | valor |
  verificador`. Los largos, el prefijo y qué significa el valor varían por
  marca y por cómo esté configurado cada equipo.
- Decisión, en tres partes:
  1. **El parser vive en LibraCommerce** (`domain/scale.py`, v0.3.0), no
     en VentaLibra: leer una etiqueta de balanza es lógica comercial y
     cualquier vertical de retail la necesita igual. Es una función pura
     sobre un `ScaleFormat`; resolver el producto y el precio queda del
     lado del consumidor.
  2. **Se soportan los dos modos** (peso embebido e importe ya calculado)
     porque cuál usa un local es configuración del equipo, no algo que se
     pueda deducir. Con peso, el sistema aplica el precio por kilo
     vigente; con importe, cobra lo que dice la etiqueta pegada al
     producto aunque el precio del sistema haya cambiado desde que se
     pesó. Traducir un importe a un peso dividiendo por el precio vigente
     se descartó: reconstruye un dato que la etiqueta no trae.
  3. **La configuración va en la base, no en variables de entorno**
     (`commerce_settings`, clave/valor): la ajusta el dueño del local
     desde una pantalla, y pedirle un redeploy para calibrar la balanza no
     es viable.
- Dos casos que se resuelven fallando y no adivinando: un `ScaleFormat`
  incoherente se rechaza **al guardarlo** (si entrara, cada etiqueta se
  leería mal hasta que alguien lo note), y una etiqueta de peso sobre un
  producto que se vende por unidad devuelve 422 en vez de cobrar "0,750"
  de algo que se cuenta — es un código de balanza cargado en el producto
  equivocado.
- Un detalle que sí importa en el mostrador: la etiqueta que se leyó bien
  pero apunta a un producto no cargado devuelve **422, no 404**. Un 404
  manda al cajero a re-escanear un código que en realidad está perfecto.
- El tipo de código nuevo `ItemCodeType.SCALE` obligó a que
  `find_item_by_code` pueda restringir por tipo: los códigos de balanza
  son números cortos que elige el comercio (7, 12, 103) y chocan con los
  códigos internos. El `UNIQUE` de `item_codes` es por (tipo, código), así
  que la colisión es legítima y hay que desambiguarla al buscar.
- Consecuencias en VentaLibra: 16 tests nuevos, y 12 en LibraCommerce.
  Pantalla nueva Configuración → Balanza, con un probador que escanea una
  etiqueta real contra la configuración guardada y muestra qué entendió el
  sistema sin registrar ninguna venta — la única forma honesta de validar
  el formato sin arriesgar un cobro equivocado. En el POS, el
  multiplicador (`3 * código`) se ignora sobre una etiqueta de balanza:
  cada etiqueta es de un paquete concreto, no de N iguales.

## ADR-020 — Cuenta corriente: el cálculo se comparte con LibraCore, la deuda entra como débito explícito

- Estado: aceptada
- Fecha: 2026-07-28
- Contexto: el fiado de barrio no es opcional en una despensa (ver
  `wiki/analyses/ventalibra-gaps-despensa.md`). LibraCore **ya tenía**
  cuenta corriente completa — saldo, movimientos, resúmenes — usada en
  producción por Contalibra y Restolibra. Pero estaba cableada a las tablas
  de esos productos: calcula el saldo con un `JOIN` contra sus ventas, y
  las de VentaLibra viven en otro archivo SQLite (el de LibraCommerce),
  donde ningún `JOIN` las alcanza.
- Alternativas evaluadas: construir una cuenta corriente propia en
  LibraCommerce (deja el concepto implementado dos veces) o espejar
  clientes y ventas en la base de LibraCore para poder usar la existente
  (mismos datos en dos bases, que divergen y vuelven el saldo poco
  confiable). Se eligió **generalizar la de LibraCore**, decisión del
  usuario: es la única que deja una sola implementación.
- Decisión, del lado de LibraCore (v0.28.0):
  1. El origen de las ventas es un parámetro (`OrigenVentas`). Eso además
     borró una duplicación que ya existía: Contalibra y Restolibra tenían
     cada uno una copia byte-a-byte del módulo para cambiar un `JOIN`.
  2. `cc_debitos`, tabla nueva, para la deuda que no nace de una venta de
     esa base. VentaLibra registra ahí el débito al confirmar la venta
     fiada. Queda vacía en los otros productos, así que su saldo no cambia.
  3. `clients.external_ref` identifica al cliente en el producto que lo dio
     de alta (`party-7`), que es lo que permite reencontrar al mismo deudor
     en su segunda compra. No espeja la cartera: **sólo entra quien fía**.
- Decisión, del lado de VentaLibra: **fiar no es cobrar**. Una venta a
  cuenta corriente no genera movimiento de caja y no entra al arqueo del
  turno; el movimiento aparece cuando el cliente paga. Si entrara, el
  cajero cerraría cuadrando contra un total que no está en el cajón. Hay un
  test dedicado a esto y su contraprueba en efectivo.
- Dos reglas que se validan antes de confirmar, no después: no se le puede
  fiar a consumidor final (una deuda tiene que ser de alguien), y la
  cobranza exige turno abierto (esa sí es plata que entra). Si fallaran
  después de confirmar, la venta quedaría cobrada sin deuda registrada en
  ningún lado.
- `PATCH /sales/{id}` aparece por una razón de mostrador: el cajero se
  entera de que la venta va fiada **al cobrar**, con las líneas ya
  cargadas. Exigir el cliente antes de la primera línea volvería el fiado
  inusable. Sólo aplica a ventas en borrador: cambiarle el cliente a una
  venta cerrada sería reescribir quién debe, sin rastro.
- Cobrar de más se acepta y queda como saldo a favor — pasa en el
  mostrador cuando el cliente redondea para arriba.
- Consecuencias: 17 tests nuevos (135 en total). Verificación de que la
  refactorización no movió plata: se comparó el saldo viejo contra el nuevo
  para los 31 clientes de la producción de Contalibra, sin diferencias.
  Pantalla nueva de Cuentas corrientes; en el POS, selector de cliente
  (F7) y el medio "Cuenta corriente (fiado)".

## ADR-021 — Ticket impreso: el generador ya existía en Contalibra, se extrajo en vez de reescribirlo

- Estado: aceptada
- Fecha: 2026-07-28
- Contexto: el ticket impreso era el tercer bloqueante del relevamiento del
  rubro. El usuario avisó que **ya estaba resuelto en Contalibra**, y al
  mirarlo apareció el mismo patrón que con la cuenta corriente:
  `ticket_generator.py` (385 líneas, PDF térmico de 58/80 mm) estaba
  **copiado byte a byte en Restolibra**, que además le sumaba su comanda de
  cocina.
- Decisión: extraerlo a `libracore.ticket_generator` (v0.29.0) y dejar a los
  dos productos en un shim. La comanda de cocina sigue siendo de Restolibra
  — no es un ticket de venta sino una orden de preparación, sin precios y
  con la letra más grande porque se lee de lejos — pero se arma sobre las
  piezas públicas del motor (`TicketPDF`, `cfg_ticket()`,
  `recortar_a_contenido()`, `fmt_fecha()`) en vez de duplicarlo. VentaLibra
  sólo aporta el puente de su `Sale` de LibraCommerce al dict que el
  generador espera.
- El módulo **no tenía tests en ninguno de los dos productos**. Se
  agregaron 14 en LibraCore que fijan el comportamiento tal como estaba al
  extraerlo, incluido que el ancho de página siga al configurado: 58 y 80
  mm son rollos distintos y equivocarlo sólo se nota con el papel puesto.
- La impresión va por el diálogo del sistema (`window.open` + `print()`),
  no directo a la impresora: el navegador no puede hablarle a la
  ticketeadora, y el diálogo del sistema es el que la conoce. El PDF ya
  sale con el ancho configurado, así que entra a la medida del rollo.
- Sólo se imprime el ticket de una venta **confirmada**: un comprobante
  impreso de algo que todavía se puede modificar miente. Y se puede
  reimprimir tantas veces como haga falta — se corta el papel, se traba la
  impresora — sin alterar la venta.
- Comportamiento conocido, dejado explícito en un test: confirmar con el
  atajo `medio_pago` (en vez de `pagos`) registra el movimiento de caja
  pero no guarda el pago en la venta, así que el ticket sale sin el
  desglose de medios. El POS siempre manda `pagos`; el atajo es de la API.
- Hallazgo del camino: `libracore.config_manager` resuelve su ruta **al
  importarse**, desde `DATA_DIR` o el cwd. Sin aislarlo, los tests que
  guardaban configuración escribían `config.json` en la raíz del repo. Se
  parchea en `conftest.py`.
- Consecuencias: 15 tests nuevos (150 en total). Pantalla nueva de
  configuración del ticket con vista previa del ancho elegido.

## ADR-022 — Anulación y devolución: el stock en LibraCommerce, el dinero en LibraCore

- Estado: aceptada
- Fecha: 2026-07-28
- Contexto: último bloqueante del relevamiento del rubro. Contalibra y
  Restolibra ya tenían `anular_venta()` **con el cuerpo idéntico** (~47
  líneas, difería sólo el docstring) — cuarta duplicación de esta clase
  encontrada el mismo día.
- Decisión: partirla por contexto, que es como ya estaba `confirm_sale`.
  `libracommerce.usecases.sales` se lleva `cancel_sale` y
  `return_sale_items` (stock y estado de la venta);
  `libracore.db.reversiones` se lleva `revertir_cobro_venta` y
  `reintegrar_devolucion` (caja y cuenta corriente). Contalibra y Restolibra
  componen la segunda con su reposición de stock propia — que se queda ahí
  porque pasa por `add_movimiento_stock`, el que sabe de recetas.
- **La reposición invierte los movimientos del ledger, no las líneas de la
  venta.** Lo que salió del depósito puede no ser el producto vendido (los
  insumos de una receta), y el ledger ya lo sabe: revertirlo así sale
  simétrico sin volver a resolver nada. Para eso aparece
  `list_stock_movements_by_source()`.
- VentaLibra orquesta las dos piezas **entre sus dos bases**, así que no hay
  transacción única. Por eso ambas partes son idempotentes por separado: un
  reintento tras una falla a mitad de camino completa lo que faltaba en vez
  de duplicar. Anular dos veces no repone dos veces; los movimientos de caja
  no se duplican por referencia.
- Dos casos se rechazan en vez de dejar pasar: devolver más de lo que queda
  sin devolver (inventaría stock y reintegraría plata que nunca entró) y
  devolver una línea de servicio suelta — cuánto se devolvió se lleva en el
  ledger de stock y un servicio no deja rastro ahí, así que se podría
  devolver infinitas veces sin control. Para eso está anular la venta entera.
- **Dos hallazgos que cambiaron el diseño, ninguno visible en los tests del
  módulo:**
  1. La primera versión omitía el movimiento de caja del pago a cuenta
     corriente por considerarlo redundante. Comparando contra el
     comportamiento anterior sobre dos bases idénticas, resultó que esa fila
     **sí existía** y desaparecía del listado de movimientos — del historial
     que ve el usuario. Los totales daban igual porque `get_caja_resumen()`
     ya filtra ese medio. Se volvió al comportamiento exacto.
  2. El egreso de la anulación no quedaba atado a ningún turno, así que **no
     descontaba del arqueo**: el cajero cerraba contando plata que ya había
     devuelto. Apareció recién al anular una venta de punta a punta
     (`libracore` v0.30.1).
- Pantalla nueva de **Ventas**: no existía ninguna forma de ver una venta ya
  cobrada — el POS la cerraba y desaparecía — así que deshacer la de ayer,
  que es cuando el cliente vuelve con el producto, era imposible. Trae
  `GET /sales` (encabezados nada más; el detalle se pide al abrir una).
- Consecuencias: 15 tests nuevos (165 en total), más 14 en LibraCommerce y
  12 en LibraCore. La devolución se puede reintegrar por un medio distinto
  del cobrado: se pagó con tarjeta y se devuelve en efectivo, que es lo que
  pasa en el mostrador.

## ADR-023 — Cobro con QR de MercadoPago: primero la plata, después la venta

- Estado: aceptada
- Fecha: 2026-08-23
- Contexto: pedido de tener en VentaLibra (y en LibraClub) la misma función
  de facturación automática con QR de MercadoPago que Contalibra tiene en
  producción desde el 2026-08-19. VentaLibra no tenía **nada** de
  MercadoPago: el medio `mercado_pago` del POS sólo etiquetaba el cobro.
- Decisión: portar el mecanismo, no reescribirlo. El cliente REST sale de
  `libracore.mp_api` (`crear_orden_qr`, `buscar_pago_por_referencia`,
  `eliminar_orden_qr`), que ya lo comparten los productos de la familia. Acá
  se agrega la orquestación: `app/services/mp_qr.py`, tres endpoints en
  `routers/sales.py` y el panel del diálogo de cobro.
- **Se invierte el orden respecto de Contalibra, y ésa es la decisión de
  fondo.** Contalibra confirma la venta y después cobra el QR, así que deja
  una ventana en la que hay una venta registrada como cobrada que en
  realidad nadie pagó. Acá el QR se pone sobre el **borrador**: se espera la
  acreditación y recién ahí se confirma, que es lo que registra caja y emite
  la factura. El agujero se invierte —si el navegador se muere entre la
  acreditación y el confirm, la plata entró y la venta no quedó registrada—
  y por eso la orden aprobada queda guardada en `sale_mp_orders` con su
  `payment_id`: el borrador sigue existiendo y volver a abrirlo lo muestra
  acreditado.
- **Sin webhook, y no es una simplificación.** En el momento en que
  MercadoPago avisaría todavía no hay ninguna venta confirmada contra la
  cual acreditar nada: el webhook no tendría qué hacer. Y el camino que en
  Contalibra **funciona** es el poll — en la instancia real del cliente no
  llegó nunca un POST al webhook, contra 5 a `mp-qr`.
- **La factura automática la decide el backend, no el checkbox del POS.** Si
  la resolviera la pantalla, cualquier otro cliente de la API cobraría por
  QR sin facturar y nada avisaría. `confirm_sale` la fuerza cuando hay una
  orden de QR acreditada y `mp_auto_facturar_ventas` está prendido — y
  **sólo si el módulo `facturacion` está en el plan**: la automática no
  puede convertir un cobro en un 403.
- Tabla propia `sale_mp_orders` (`app/db.py`), mismo patrón que
  `party_billing` y `party_roles`: FK contra `sales` sin agregarle columnas
  al esquema de LibraCommerce, que comparten cinco productos. Una fila por
  **intento**, con `external_reference` aleatoria por intento: reusarla haría
  que un pago rechazado que MercadoPago acredita tarde vuelva como aprobado
  para el intento siguiente, que puede ser por otra plata.
- `DELETE /sales/{id}/mp-qr` baja la orden del cartel. **Contalibra no llama
  nunca a `eliminar_orden_qr`** — no tiene un solo call site en todo el
  repo — así que depende de que el cliente siguiente no escanee antes de que
  el cajero cargue la venta nueva. Acá lo llaman el botón de cancelar, el
  cierre del diálogo y el vencimiento de la espera.
- **Pide `libracore` v1.40.0 o más, y casi nace roto por eso.** Cuando esto se
  empezó, el producto pineaba **v1.39.2**, donde `crear_orden_qr` pegaba a una
  URL que no existe (404 contra una cuenta real) y hacía `r.json()` sobre una
  respuesta 204 sin cuerpo. El arreglo llegó en la v1.40.0, verificado contra
  la cuenta real de Contalibra. Para cuando esto se integró, el pin ya estaba
  en **v1.45.0** por otro motivo —la zona horaria de la plantilla de
  provisioning—, así que no hizo falta subirlo: lo que quedó en
  `pyproject.toml` es **el piso**, anotado. Bajar el pin por debajo de v1.40.0
  rompe el cobro sin que nada avise — la URL mal armada la contesta MercadoPago
  con el mismo 404 que un POS ID inexistente.
- **Deuda que queda anotada, no arreglada** *(cerrada el 2026-08-24 por
  ADR-024)*: este POS escribe el medio como
  `mercado_pago` con guion bajo y el resto de la familia usa `mercadopago`
  pegado, que es la clave de `MEDIOS_PAGO_LABELS` de LibraCore. Ya hay
  movimientos de caja guardados con la forma de acá, así que normalizarla es
  una migración de datos aparte. Mientras tanto `MEDIOS_QR` acepta las dos.
- Consecuencias: 21 tests nuevos de backend (295 en total) y 6 de frontend
  (20 en total). Sección nueva **Mercado Pago** en Configuración, con las
  tres credenciales y el toggle de la automática.

## ADR-024 — La grafía de MercadoPago: primero los datos, después el selector

- Estado: aceptada
- Fecha: 2026-08-24
- Contexto: este POS escribía el medio como `mercado_pago`, con guion bajo, y
  los otros diez repos de la familia usan `mercadopago` pegado, que es la
  clave de `libracore.medios_pago.ELEGIBLES`. Era la **última divergencia de
  grafía** del vocabulario de medios de pago, y estaba declarada en **tres**
  listas del frontend —`Pos.tsx`, `CuentasCorrientes.tsx`, `Ventas.tsx`—, más
  una constante `MERCADO_PAGO` en `Pos.tsx` que la lista de esa misma pantalla
  duplicaba en vez de usar.
- **No se podía arreglar con un `sed`, y ésa es la decisión de fondo.** Hay
  filas escritas con la grafía vieja. Cambiar el selector sin tocarlas parte
  cada reporte en dos líneas para la misma cosa: la plata bien contada y el
  reparto mal, que es exactamente el defecto que el vocabulario unificado vino
  a cerrar. El orden es **primero los datos y después la grafía**.
- Decisión: una **normalización que corre en cada arranque**
  (`app/normalizacion_medios.py`), enganchada en los dos puntos donde este
  producto abre sus bases: `db.connect()` para el dominio y
  `billing.configure()` para la de LibraCore.

### Por qué en cada arranque y no una migración numerada

Es la forma menos habitual y es deliberada. El paso siguiente del trabajo de
familia es **sacar `mercado_pago` de `libracore.medios_pago.HISTORICOS`**, y a
partir de ahí `label()` devuelve el slug crudo para cualquier fila que la
tenga. Una base restaurada desde un backup anterior a esta versión vuelve a
tener filas así, y una migración ya marcada como aplicada **no la volvería a
tocar**. Corriendo en cada arranque, una restauración se arregla sola al
levantar el contenedor. El costo es seis `UPDATE ... WHERE` que no matchean
nada.

### Qué se toca, y por qué la lista no salió de leer el código

La lista de columnas salió de **recorrer todas las columnas de texto de las dos
instancias reales** buscando el literal, no de leer los `INSERT` del repo. El
barrido que uno escribe por reflejo —filtrar `column_name LIKE '%medio%'`—
encontraba `caja_movimientos.medio_pago` y `cc_pagos.medio_pago` y **se perdía
`recibos.pagos`**, que guarda el medio adentro de un JSON en una columna que no
se llama nada parecido. Por eso el test de guarda escanea la base entera en vez
de chequear la lista del módulo: un control que comparte el criterio con lo que
verifica hereda su punto ciego.

Son seis lugares: `sale_payments.method` (LibraCommerce) y, en LibraCore,
`caja_movimientos.medio_pago`, `cc_pagos.medio_pago`, `egresos_pagos.medio_pago`,
`ventas_pagos.medio` y los dos JSON (`cajas.medios_pago`, `recibos.pagos`).

### El snapshot del recibo se reescribe, y el papel MEJORA

`recibos.pagos` es el snapshot de un comprobante ya emitido, así que tocarlo hay
que justificarlo sobre el papel y no sobre la fila. Medido: el
`_MEDIOS_LABEL` de `libracore.pdf_generator` **nunca conoció `mercado_pago`**,
así que el recibo de una cobranza por MercadoPago venía imprimiendo el slug
crudo, con guion bajo, en la columna «Medio» de un comprobante que se le entrega
al cliente. Con la grafía normalizada imprime la etiqueta. El resto del
comprobante queda idéntico, y el test lo afirma comparando el **texto extraído
del PDF** completo antes y después, no la fila.

### Lo que este ADR NO hace

Sacar `mercado_pago` de `libracore.medios_pago.HISTORICOS`. Ese es el último
paso y va **sólo cuando no queden filas en ninguna instancia**, con el pin de
LibraCore subido. Hay un test en LibraCore que se pone rojo si se intenta antes:
es un trinquete deliberado, y su rojo es la señal de ir a verificar los datos,
no de editarlo.

- Consecuencias: 5 tests nuevos de backend y 1 archivo de guarda nuevo en el
  frontend (`sin-grafia-vieja-de-mercadopago.test.ts`, 5 tests), que impide que
  la grafía vuelva por cualquiera de las tres listas. La medición previa sobre
  las 24 instancias PostgreSQL del VPS está en
  `wiki/concepts/medios-de-pago-familia-libra.md`.

## ADR-025 — La venta pasa a la capa ERP de LibraCommerce (plan post-P9)

- Estado: aceptada
- Fecha: 2026-09-13
- Contexto: VentaLibra vende hoy con los casos de uso **viejos** del motor
  (`usecases/sales.py`): un borrador que se llena por posición y se confirma
  después contra `confirm_sale`, que sólo descuenta stock y deja
  `reason_code` en NULL. Numeración propia `POS-000001` con la tabla
  `sequences`; caja, cuenta corriente y factura los orquesta el router fuera
  de toda transacción, con IVA fijo al 21 %; un turno único para toda la
  instancia. No usa la capa `erp/` + `web/` que Contalibra y Restolibra
  adoptaron en la migración P9 — la de `crear_venta_links` y las factories de
  routers de LibraCore. Pasar a esa capa no es cambiar imports: cambia el
  modelo de la venta (borrador → registrar en una sola llamada) y cambia
  datos ya guardados. El plan completo, con la brecha medida contra el motor
  el 2026-09-11, está en el wiki (`plan-ventalibra-a-libracommerce`). Antes
  de F1 se vuelve a medir sobre `develop`: el motor se movió desde entonces.
- Decisión: las seis que contestó el humano el 2026-09-13. D4 y D5 eran la
  recomendación del plan y el humano las aceptó sin objeción:

  | | Decisión |
  |---|---|
  | **D1** Borrador | El POS arma la venta **en el navegador** y la registra en una sola llamada, como Contalibra |
  | **D2** Cobro por QR | El **modelo de la familia**: venta pendiente y `acreditar_pago_qr` |
  | **D3** Cuenta corriente | **Modelo derivado**: se migran los `cc_debitos` y se alinean los ids |
  | **D4** Vuelto | **Se guarda** (columna `recibido` en `ventas_pagos`) |
  | **D5** Numeración | **Se mantiene `POS-`** |
  | **D6** Alcance | **Todo junto**: catálogo, listas de precio y reportes también pasan ahora a las factories |

- **El mismo día se sumaron decisiones que cambian el alcance**, por fuera de
  D1–D6: varias cajas por sucursal, con la sucursal como el **depósito**
  (`Location` de LibraCommerce, id entero, entra en `cajas.sucursal_id` sin
  tocar el schema); punto de venta de ARCA por sucursal, como LibraClub; y QR
  de MercadoPago **por caja**, calcado del punto de venta por caja que ya
  resuelve LibraCore (`resolver_punto_venta`), así que Contalibra y Restolibra
  lo heredan sin tocar su código. Queda por confirmar contra MercadoPago si el
  collector (`mp_user_id`) es de la cuenta o de la caja, y si un pago informa
  desde qué caja salió. **Las cajas múltiples y el cierre diario de VentaLibra
  van después de este plan**, no en paralelo — orden fijado por el humano.
- **El relevamiento de D6 encontró que LibraCommerce ya tiene** variantes y
  precios con vigencia y por sucursal en el dominio y en el schema
  (`item_variants`, `item_prices` con `valid_from`/`valid_until`/`branch_id`),
  y VentaLibra ya los usa. Lo plano a propósito es la capa `erp/` + `web/`
  (`erp/listas_precio.py` fuerza un sentinel de vigencia y `branch_id IS
  NULL`): el trabajo es extenderla de forma aditiva, sin cambiarle nada a
  Contalibra ni a Restolibra. La pantalla de catálogo con variantes en
  libra-ui es nueva de punta a punta.

### F0, contado el 2026-09-13

Lectura de sólo lectura (`default_transaction_read_only`) en `ventalibra-dev`
y `ventalibra-demo`:

| | dev | demo |
|---|---|---|
| Ventas | 7 confirmadas y 3 borradores abandonados (más de un día) | 4 confirmadas, 1 anulada y 1 borrador |
| Líneas de venta, stock y catálogo con variante | 0 | 0 |
| Precios con vigencia cerrada o por sucursal | 0 (`item_prices` vacía) | 0 |
| Pagos con vuelto guardado | 1 de 1 | 3 de 5 |
| Órdenes QR (`sale_mp_orders`) | 0 | 0 |
| `cc_debitos` | 3, $18.000 | 1, $40.800 |
| `ventas_pagos` | 0 | 0 |
| Cajas | 1 caja sin sucursal y 2 depósitos | la salida se cortó antes de esa parte |

🔑 **Hallazgo de F0, en demo: la venta a cuenta corriente está contada dos
veces** — como débito ($40.800 en `cc_debitos`) y como pago con medio
`cuenta_corriente` ($40.800). Es exactamente el doble conteo que anticipa D3
al pasar al modelo derivado: LibraCore también deriva deuda de `ventas_pagos`
con `cuenta_corriente`, así que migrar los pagos fiados y mantener
`cc_debitos` tal cual duplicaría la deuda. La migración tiene que llevar **uno
solo** de los dos registros por venta a cuenta corriente, y el invariante que
lo atrapa es *"el saldo de cada cliente da igual"* antes y después.

### Fases

| Fase | Qué | Repo | Gate |
|---|---|---|---|
| **F0** | Contar borradores, precios con vigencia/sucursal, líneas con variante, `cc_debitos`, QR pendientes, vuelto guardado, en dev y demo | VentaLibra + wiki | esta ADR-025 con D1–D6 escritas |
| **F1** | Extensiones del motor; `anular_venta` tolerante a filas viejas por condición (`source_type='sale' AND movement_type='sale'`), sin `UPDATE` sobre el ledger inmutable | LibraCommerce | suite verde + mutaciones dirigidas; Contalibra y Restolibra sin tocar con el pin nuevo; tag |
| **F2** | QR en `ventas_cobro_router`; columna `recibido` en `ventas_pagos`; cotejar el resumen de turno de `build_turnos_router` con el de VentaLibra | LibraCore | suites de LibraCore y productos verdes; tag |
| **F3** | Ganchos, factories, revisión de migración `0002` con `downgrade`; `/sales` queda de sólo lectura | VentaLibra | invariantes portados (ventas, devoluciones, cuenta corriente, QR, reportes); test de migración upgrade → conteos → downgrade; mutaciones muertas; cobertura ≥ piso |
| **F4** | `Pos.tsx`, `Ventas.tsx` de libra-ui; reescribir el seed de demo; sacar `/sales` | VentaLibra + libra-ui | tests de frontend, smoke de navegador |
| **F5** | Deploy: `ventalibra-dev` primero (backup, cadenas de migración, conteos, verificación por contenido), después `demo` | VPS | — |

F1 y F2 pueden ir en paralelo. Esta vez no hay "suite sin tocar" en el
producto: la API cambia, así que el gate son los invariantes portados, no la
suite vieja intacta.

### Consecuencias y riesgos visibles para el cliente

- **La factura pasa del IVA fijo al 21 % a las alícuotas de
  `venta_facturacion`**: cambia el comprobante que recibe el cliente.
- **El reporte por día local, arreglado el 2026-08-25, tiene que sobrevivir**
  al pasaje a `erp/reportes`, que filtra por `occurred_on` — verificar que no
  vuelva el defecto que ese arreglo cerró.
- **`/sales` queda de sólo lectura en F3 y se saca recién en F4**, pero el POS
  pasa a `/api/ventas` recién en F4. Por eso **F3 no se despliega sola**: F3 y
  F4 llegan juntas a dev y a demo en F5. Desplegar F3 sin F4 dejaría el POS
  escribiendo contra una ruta de sólo lectura, sin poder vender.

### Lo que este ADR NO hace

No implementa nada de F1 a F5 — es la decisión de alcance y orden, no el
código. No cambia la numeración (D5 mantiene `POS-`). No toca cajas múltiples
ni cierre diario de VentaLibra: esas quedan **después** de este plan, por
decisión explícita del humano, y no forman parte de esta ADR.

- Consecuencias: plan de seis fases (F0–F5) sobre dos repos motor
  (LibraCommerce, LibraCore) y VentaLibra; con esta ADR se cierra F0. El
  detalle de la brecha, las decisiones D1–D6 y los lugares donde el motor,
  tal como está, rompería a VentaLibra en silencio están en
  `plan-ventalibra-a-libracommerce` (wiki).

## ADR-026 — Cajas por sucursal, turno por caja y cierre diario

- Estado: aceptada
- Fecha: 2026-09-16
- Contexto: F3 y F4 del plan post-P9 (ADR-025) ya están en `develop`
  (`feature/f3-capa-erp`, `feat(pos): ... se retira /sales`, ambos del
  2026-09-15): el POS vende contra `/api/ventas`, la capa ERP de
  LibraCommerce. Con eso cerrado, esta ADR hace lo que ADR-025 dejó
  explícitamente para después: **el cliente real tiene dos locales vendiendo
  a la vez**, y hoy hay una sola caja y un turno compartido para toda la
  instancia (`get_turno_activo_any`) — dos cajeros en dos locales mezclan su
  plata en el mismo arqueo.
- Decisiones del humano:

  | | Decisión |
  |---|---|
  | Sucursales | Varias cajas **por sucursal** — la sucursal es el `Location` de LibraCommerce (el mismo id que ya usa el depósito) |
  | Punto de venta | Por **caja**, como ya resuelve el motor (`resolver_punto_venta`: usuario → turno → caja → punto de venta); nullable = el de la empresa |
  | QR de MercadoPago | Fuera de alcance — sigue uno por instancia |
  | Cierre diario | Acto registrado y numerado por sucursal, con ticket de 80 mm de cada turno y del día; lo puede hacer admin **o cajero** |
  | Anular/devolver | El cajero sigue pudiendo — no se agrega `solo_admin` al router de ventas |

- Decisiones propias (no pedidas explícitamente, resueltas al construir):
  - **El turno pasa de compartido a por usuario y por caja** (`libracore.db.
    turnos.get_turno_activo`, el default del motor) en vez de inventar un
    tercer modelo. Es lo mínimo que separa la plata de dos cajeros: cada uno
    tiene el suyo, en su caja.
  - **"Una caja, un turno a la vez" es una regla de este producto, no del
    motor.** Ni siquiera LibraClub —la otra instancia con cajas múltiples—
    la impone (sólo evita que un mismo usuario tenga dos turnos). Sin ella,
    dos cajeros podrían abrir turno en el mismo mostrador y mezclar la plata
    igual que antes. Se valida en `app/routers/shifts.py` con una consulta
    propia (`app/services/cajas.py::turno_abierto_de`), compartida con el
    router de cajas para no ofrecer al abrir una que ya está en uso.
  - **La caja por defecto es por sucursal, no global.** El motor
    (`db_caja.set_default_caja`) hace `UPDATE cajas SET es_default=0` sin
    filtrar — correcto para los productos sin sedes, pero acá le borraría la
    predeterminada a las demás sucursales. Se reimplementa en
    `app/services/cajas.py::marcar_predeterminada`, calcado del mismo fix ya
    hecho en LibraClub para el mismo caso.
  - **Nada valida que `deposito_id` de `POST /api/ventas` sea la sucursal de
    la caja del turno — ni se agrega.** Investigado activamente: ni
    `VentaPayload` ni `Hooks` (`libracommerce/erp/hooks.py`) ofrecen un punto
    de extensión que llegue a un 422 limpio sin tocar el motor o reusar
    `DepositoInexistente` con un mensaje que mentiría (el depósito SÍ
    existe, es de otra sucursal). Se resuelve en el frontend: con turno
    abierto, el POS fija la sucursal a la de la caja del turno y saca el
    selector — ver el comentario largo en `app/routers/shifts.py` y en
    `frontend/src/pages/Pos.tsx`. Pendiente de motor, reportado con archivo y
    línea en el primero.
  - **Cerrar un turno sigue sin exigir ser el dueño ni admin** — así estaba
    antes de esta feature (cualquier staff/admin podía cerrar cualquier
    turno). Restringirlo a "dueño o admin" habría sido un cambio de permisos
    que nadie pidió; se documenta la decisión de no tocarlo en
    `app/routers/shifts.py::cerrar`.
  - **`libracore` sube a v1.104.0** (de v1.102.0) para no quedar más de un
    pin atrás del resto de la familia mientras se agrega esta feature. Sin
    migraciones nuevas para VentaLibra en el camino — v1.103.0 y v1.104.0
    tocan `libracore-migrar`/`panel_admin.py`, no el schema. La migración
    `0009_cierre_diario` (cajas, cierres_diarios\*) ya estaba en la cadena
    desde antes de este pin.
- Lo que NO cambia: la capa ERP (D1–D6, ADR-025), la numeración `POS-`, el
  QR por instancia, y el gate de anular/devolver del cajero.
- Consecuencias: `app/services/cajas.py` y `app/routers/cajas.py` (ABM de
  cajas), `app/routers/shifts.py` reescrito (turno por usuario y caja, guarda
  de caja-única), `app/ganchos.py::turno_para` y `app/routers/accounts.py`
  dejan de usar `get_turno_activo_any`, `libracore.caja_router.
  build_cierre_diario_router` montado, y `frontend/src/pages/Cajas.tsx` +
  `CierreDiario.tsx` nuevas. Datos existentes: instancias reales pueden tener
  turnos abiertos sin caja y cajas sin sucursal — el arranque los reasigna
  (`app/services/cajas.py::asegurar_cajas_de_todas`) y los turnos viejos
  siguen viéndose y cerrándose (`app/routers/shifts.py::_enriquecer`
  tolera `caja=None`).

## ADR-027 — La cuenta corriente adopta la pantalla del kit (P9-M4)

- Estado: aceptada
- Fecha: 2026-09-24
- Contexto: desde P9-M4 (2026-09-07) Contalibra y Restolibra montan las
  pantallas del kit (`libra-ui/comercio/CuentaCorriente` +
  `CuentaCorrienteDetalle`). VentaLibra quedó como el único producto de la
  familia con una pantalla propia, sin detalle por cliente, sin pagar desde
  la pantalla y sin baja de pago. Con ADR-026 (turno por caja) y P9-M3 (QR
  por caja) cerrados, el port era lo que faltaba para que las cuentas
  corrientes quedaran normalizadas en toda la familia.
- Decisiones del humano: adoptar el modelo de Contalibra — las pantallas del
  kit, con las reglas de VentaLibra intactas.
- Decisiones propias (no pedidas explícitamente, resueltas al construir):
  - **El negocio no se copió: se expone.** El motor ya estaba
    (`CuentaCorrienteService` + `/accounts`); el nuevo
    `app/routers/cuenta_corriente_api.py` traduce el contrato que el kit
    llama a fuego (`/api/cuenta-corriente*`, `/api/recibos/*`) a ese mismo
    servicio. `/accounts` queda como está — lo que cambia es la pantalla, no
    la API vieja.
  - **Las reglas de este producto van en el backend, no en la pantalla.** El
    kit lo usa igual Contalibra (que ofrece todas las cajas para cobrar);
    acá el cobro exige turno abierto (409), cae en la **caja del turno** de
    quien cobra, `GET /api/cuenta-corriente/cajas` devuelve sólo esa caja —
    ofrecer las demás sería ofrecer algo que el arqueo no cuenta — y si
    `caja_id` viene con otra es 422. `cuenta_corriente` no es un medio de
    cobro (422), igual que `CobranzaIn`.
  - **Los montos del contrato del kit viajan como números.** El kit compara
    `saldo > 0` y suma montos en el navegador; un `Decimal`-string los
    concatenaría. (El router `/accounts` sigue serializando Decimal: su
    pantalla propia se fue con este cambio.)
  - **La referencia del movimiento de caja es siempre `cc-pago-<id>`.** La
    que escribe el usuario vive en `cc_pagos` (visible en la cuenta y en el
    recibo). Sin el tag fijo, la baja de pago no puede encontrar el ingreso:
    hoy todo pago nuevo es bajable; los viejos (referencia a mano) se
    rechazan con 409 — mejor un error que un ingreso huérfano contando plata
    en el arqueo.
  - **La baja de pago (admin) anula recibo y movimiento, después borra el
    pago** — en este orden. El recibo no se borra (el número se consumió y
    el papel pudo haber salido) y el movimiento de caja no se borra (pedido
    del humano, 2026-08-28): anulado queda la fila para auditar y sale de los
    totales.
  - **Los links fijos del kit que este producto no tiene, redirigen.** El
    "Volver" del detalle va a `/cuenta-corriente` y la "Ficha cliente" a
    `/clientes/:id`: sin ruta, ambos caerían al catch-all y parecería que se
    rompió el sistema (mismo criterio que las redirecciones de
    Configuración). Viven en `rutas-viejas.ts` (`REDIRECCIONES_DEL_KIT`), no
    como `<Route path="...">` literales: el guard de títulos
    (`libra-ui/auditoria-de-titulos`) atribuye a cada `path` literal la
    primera pantalla que aparece en la ventana de 500 caracteres siguiente,
    así que un `<Navigate>` en el medio les colgaba a las redirecciones el
    icono de la pantalla vecina (`/clientes/:id` heredaba el de Stock). Queda
    pendiente la ficha (este producto no la tiene); `/facturas/:id` no ocurre
    acá porque las deudas nacen de ventas fiadas, no de facturas.
- Lo que NO cambia: `/accounts` (endpoints y serialización), el listado en la
  navegación (`/cuentas-corrientes`), `libra-ui` (el kit ya traía todo) ni
  las reglas de fiado de ADR-024/025.
- Consecuencias: `app/routers/cuenta_corriente_api.py` (nuevo) y
  `app/services/cuenta_corriente.py` (`fecha`/`caja_id` en
  `registrar_cobranza`, `listado_kit`/`detalle_kit`/`eliminar_pago` +
  `SinPago`/`SinMovimientoDeCaja`), `frontend/src/pages/CuentasCorrientes.tsx`
  reescrita como montaje del kit, `CuentaCorrienteDetalle.tsx` (nueva) y tres
  rutas en `App.tsx`. Tests: `tests/test_cuenta_corriente_kit.py` y
  `frontend/src/test/cuenta-corriente-kit.test.tsx`.

## ADR-028 — Las personas pasan al modelo del motor: cliente = party de igual id, proveedor = party + 100.000

- Estado: aceptada
- Fecha: 2026-09-26
- Contexto: el humano fijó el criterio de que **Contalibra es la referencia** (de ahí salen los
  motores transversales) y que VentaLibra **adopta esos motores y esos módulos**, con sus variantes
  como extensiones del motor y no como código paralelo (inventario:
  `wiki/analyses/inventario-adopcion-motores-ventalibra-2026-09-26.md`). Clientes y proveedores no se
  podían adoptar «montando el router» porque VentaLibra guardaba personas en `parties` (dominio) y
  **espejaba** cada cliente en `clients` con otro id (`external_ref = party-<id>`), lo que obligó a los
  puentes `cliente_cc_de`, `nombre_de_cliente`, el `obtener` traducido de `venta_facturacion` y el
  origen `VENTAS_LIBRACOMMERCE_POR_EXTERNAL_REF` de cuenta corriente (ADR-025, D3).
- Decisión: adoptar la convención del motor (`libracommerce/scripts/migrate_from_contalibra.py`,
  `libracore.db.clients._espejar_party`): **el cliente vive en `clients` y su party espejo tiene el
  MISMO id; el proveedor vive en `proveedores` y su party es `proveedores.id + 100.000`.**
- Qué cambia:
  - Migración `0004_personas_del_motor` (sólo PostgreSQL): renumera los parties y todo lo que apunta a
    ellos (`sales`, `purchase_orders`, `purchase_receipts`, `party_billing`, `party_roles`) por un
    espacio de ids temporal, crea los `proveedores`, completa `clients` desde `party_billing`, y deja
    todo registrado en `_migracion_0004` para un `downgrade()` exacto. Ensayada sobre copias de los
    datos reales de dev y demo (invariantes, idempotencia, reversión).
  - `CustomerService` y `SupplierService` se reescriben sobre `libracore.db.clients` y
    `libracore.db.egresos`; se retiran los puentes; la cuenta corriente cruza con el origen
    `VENTAS_LIBRACOMMERCE` (por id), el mismo de Contalibra.
- Consecuencias, dichas de frente:
  - Un CUIT/DNI repetido entre clientes ahora se rechaza (regla del motor; antes se permitía). El servicio de la fase 1 lo devolvía como 409; con el router del motor (ADR-029) es **422**.
  - El alta de un cliente o de un proveedor **ya no queda en `actividad_log`** (no pasa por el
    repositorio auditado de LibraCommerce); Contalibra tampoco la registra. Auditarla sería un
    cambio del motor.
  - `parties`, `party_roles`, `party_billing` y `clients.external_ref` **no se borran**: quedan como
    espejo y procedencia. Retirarlos es una limpieza posterior.
  - `GET/POST /customers` y `/suppliers` se conservan como capa fina para el POS, Clientes y Compras;
    las fases 2 y 3 los reemplazan por los routers del motor. `/suppliers` sigue exponiendo el id del
    **party** (el `supplier_party_id` de las compras) hasta la fase 3.
- Alternativas descartadas: adaptadores de backend que espejen datos y parametrizar el kit para que se
  acomode al modelo de VentaLibra — ambas mantienen a VentaLibra distinto de Contalibra.

## ADR-029 — Clientes con el router del motor y la pantalla del kit (fase 2 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-26
- Contexto: con las personas ya en el modelo del motor (ADR-028), Clientes puede adoptar lo mismo que
  Contalibra y Restolibra: `libracore.clientes_router.build_clientes_router()` (`/api/clientes`) y las
  pantallas `libra-ui/comercio/Clientes` y `ClienteDetalle`. VentaLibra tenía `pages/Clientes.tsx`,
  `pages/ClienteDetalle.tsx`, `routers/customers.py` y `services/customers.py` propios.
- Decisión: montar el router del motor y las pantallas del kit; **retirar `/customers`** y el servicio.
  Las diferencias de VentaLibra entran como **variantes del kit**, no como código propio:
  `libra-ui` v0.75.0 agrega a `ClienteDetalle` las props `conMercadoPago`, `conComprobantes` y
  `conConsultaCuit`, y a `Clientes` la prop `conConsultaCuit` (todas `true` por defecto: Contalibra y
  Restolibra no cambian). VentaLibra las apaga: no tiene facturas/presupuestos/remitos, ni la bandeja
  de MercadoPago, ni `/api/consultar-cuit`.
- Consecuencias:
  - Los clientes inactivos aparecen en el listado del motor (la pantalla los marca): el POS los filtra.
  - **Un cajero (staff) ahora puede editar y dar de baja clientes** (antes `/customers` sólo creaba y
    leía). Es el comportamiento de Contalibra; si hace falta restringirlo, es un cambio del router del
    motor.
  - Sin consulta de CUIT en ARCA por ahora: el endpoint es código propio, duplicado, de Contalibra y
    Restolibra. Pendiente: extraerlo a un `build_consultar_cuit_router` en `libracore` y activarlo acá.
  - El alta de un cliente no queda en `actividad_log` (ADR-028).
- Depende de: `libra-ui` v0.75.0 publicado y el pin de este repo subido a esa versión.

## ADR-030 — Proveedores con el router del motor y la pantalla del kit (fase 3 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-26
- Contexto: con las personas en el modelo del motor (ADR-028) y Clientes adoptado (ADR-029), Proveedores
  puede usar lo mismo que Contalibra y Restolibra: `libracore.egresos_router.build_proveedores_router()`
  (`/api/proveedores`, tabla `proveedores`) y las pantallas `libra-ui/comercio/Proveedores` y
  `ProveedorDetalle`. VentaLibra tenía `pages/Proveedores.tsx`, `routers/suppliers.py` y
  `services/suppliers.py` propios, y Compras hablaba en ids de **party** (`proveedores.id + 100.000`).
- Decisión: montar el router del motor y las pantallas del kit; **retirar `/suppliers`** y su servicio.
  La ficha del kit trae los egresos del proveedor, un módulo que VentaLibra no tiene: `libra-ui` v0.76.0
  agrega la variante `conEgresos` (default `true`: Contalibra y Restolibra no cambian) y VentaLibra la apaga.
- **Compras habla en `proveedor_id`** (el `proveedores.id` del motor): `POST /purchase-orders` y
  `/purchase-receipts` reciben `proveedor_id`, y las respuestas traen `proveedor_id` además de
  `supplier_party_id`. La convención de ids del party (`id + 100.000`) queda en **un solo lugar**,
  `app/services/proveedores.py`, que además crea o refresca el party espejo **al comprarle** (el router del
  motor no sabe de compras, así que un proveedor puede nacer sin party).
- **Guarda de baja:** el router del motor sólo impide eliminar un proveedor con egresos; VentaLibra no tiene
  egresos sino órdenes y recepciones de compra. `app/proveedores_guarda.py` es una dependencia del
  `include_router` que devuelve 409 al eliminar un proveedor con compras (la factory no ofrece un gancho).
- Consecuencias:
  - Un cajero (staff) puede editar y dar de baja proveedores (comportamiento de Contalibra), igual que con
    los clientes.
  - Los proveedores ya migrados (ADR-028) siguen valiendo: su party ya tiene el id `proveedores.id + 100.000`.
  - Sin ficha de compras por proveedor: la ficha del kit no las conoce (queda como mejora).
- Depende de: `libra-ui` v0.76.0 publicado y el pin de este repo subido a esa versión.

## ADR-031 — Cuenta corriente con el router del motor (fase 4 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-26
- Contexto: ADR-027 adoptó las pantallas del kit de cuenta corriente pero dejó el **backend propio**
  (`/accounts`, `/api/cuenta-corriente` y `services/cuenta_corriente.py`, unas 600 líneas) porque el router del
  motor (`libracore.cuenta_corriente_router`) no soportaba las reglas de cobro de este producto: el cobro exige
  turno abierto y cae en la caja del turno, el selector ofrece sólo esa caja, el movimiento de caja lleva la
  referencia `cc-pago-<id>` y la baja de un pago anula ese movimiento. Con las personas en el modelo del motor
  (ADR-028) el cruce ya es por id, así que el router del motor sirve tal cual salvo esas reglas.
- Decisión: agregar al router del motor **variantes** en vez de reescribirlo (criterio del humano: los motores
  se adoptan y las diferencias entran como opciones). `libracore` v1.111.0 suma `OpcionesCuentaCorriente` con
  tres ganchos opcionales —`validar_pago`, `cajas` y `al_eliminar_pago`— que, sin pasarlos, dejan el
  comportamiento de Contalibra intacto. VentaLibra monta el router con sus ganchos
  (`app/cuenta_corriente_ganchos.py`) y **retira `/accounts`, el router propio del kit y el servicio**.
- Consecuencias:
  - Los pagos ahora se registran con `POST /api/cuenta-corriente/{id}/pagar` (con `fecha`, como Contalibra);
    `/accounts/*` desaparece. El listado devuelve `{clientes, total_deuda}`.
  - El concepto del movimiento de caja pasa a ser `Pago CC - <cliente>` (el del motor).
  - Los recibos siguen en un router propio mínimo (`app/routers/recibos.py`: emitir el de un pago y bajar el PDF):
    en Contalibra y Restolibra también es código de cada producto, sin factory. **Deuda:** extraerlo a `libracore`.
  - La baja del pago corre el gancho **antes** de anular los recibos y de borrarlo: si el movimiento de caja no se
    puede identificar, no se toca nada (antes los recibos quedaban anulados y el pago vivo).
- Depende de: `libracore` v1.111.0 publicado y el pin de este repo subido a esa versión.

## ADR-032 — Cajas y turnos con los routers del motor y las pantallas del kit (fase 5 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-26
- Contexto: la feature de cajas por sucursal (2026-09-16) escribió `/shifts` (`app/routers/shifts.py`) y el ABM
  de `/api/cajas` (`app/routers/cajas.py`) porque el motor (`libracore.caja_router`) no sabía de sucursales. El
  turno se abría y cerraba **sólo dentro del POS**: VentaLibra no tenía pantalla de turnos. Desde entonces el motor
  tiene `build_cajas_router` y `build_turnos_router` (los de Contalibra y Restolibra) y el kit tiene `Cajas`,
  `Turnos`, `TurnoDetalle` y `TurnoCerrar`.
- Decisión: adoptar los routers y las pantallas y expresar lo propio como **variantes** (criterio del humano:
  el motor es la referencia y las diferencias entran como opciones con default = Contalibra).
  - `libracore` v1.112.0: `OpcionesCajas` (`autorizar_escritura`, `validar_alta`, `validar_edicion`,
    `al_desactivar`, `predeterminar`, `enriquecer`), `sucursal_id` en la caja, `tiene_turno_abierto`,
    `validar_apertura` y `enriquecer` en los turnos, `GET /api/turnos/actual` y el 409 de un día cerrado (era 500).
  - `libra-ui` v0.77.0: `Cajas` con `sucursales`, `conActivarDesactivar` y `verMovimientos`; `Turnos` con
    `conCaja`; el detalle y el cierre muestran la caja y la sucursal si el turno las trae.
  - VentaLibra declara sus reglas en `app/cajas_ganchos.py` y **retira `/shifts`, el router de cajas y el de medios**
    (la ruta `/api/cajas/medios-disponibles` la sirve el motor).
- Consecuencias:
  - **El POS pasa a los endpoints del motor:** `GET /api/turnos/actual`, `POST /api/turnos/abrir`,
    `GET /api/turnos/{id}` (turno + resumen) y `POST /api/turnos/{id}/cerrar`. El turno se devuelve pelado, no
    `{turno}`; cerrar un turno ya cerrado es 422 (antes 409).
  - **Cambio de permisos:** el cajero ve y cierra **sólo sus turnos**, el admin los de todos (regla del motor).
    Antes cualquier sesión de staff podía cerrar cualquier turno.
  - `PUT /api/cajas/{id}` **reemplaza** los campos (contrato del motor): si no manda `mp_pos_id`, se borra. El kit
    manda siempre todos; ya no se conserva el valor omitido.
  - `activo` y `es_default` viajan como 1/0 (el motor); el frontend los lee con `!!`.
  - La sesión de este producto trae el `id` como texto y el router de turnos lo compara con un entero: el montaje
    usa `usuario_actual` (`app/cajas_ganchos.py`), que lo normaliza. Sin eso un cajero no vería ni su turno.
  - El arqueo sigue siendo **sobre la caja y sin la cuenta corriente** (ADR-027); la lista de ventas del turno sale
    de la capa ERP (`resumen.ventas`), que es lo que lee la pantalla del kit.
  - VentaLibra gana la pantalla de **Turnos** (lista, detalle con recaudación y ventas, arqueo de cierre), con
    la caja y la sucursal de cada uno. El POS conserva su propio diálogo de apertura y cierre.
  - **Cajas usa la disposición del kit** (tarjetas con botones de ícono y texto), no la tabla de acciones con sólo
    íconos que se había armado el 2026-09-26.
- **Queda afuera:** los movimientos de caja (`build_caja_router` y `libra-ui/comercio/Caja`), que VentaLibra no tiene
  hoy: entra con la fase de tesorería (9).
- Depende de: `libracore` v1.112.0 y `libra-ui` v0.77.0 publicados y los pines de este repo subidos.

## ADR-033 — Sucursales, depósitos, stock y transferencias con los routers del motor y las pantallas del kit (fase 6 de la adopción)

- Estado: aceptada; **las reglas de los dos tipos `store`/`warehouse` y de «sólo `store` vende» quedaron reemplazadas por ADR-044**
- Fecha: 2026-09-26
- Contexto: VentaLibra tenía `/locations` (`app/routers/locations.py`, `services/locations.py`), `/stock` (`app/routers/stock.py`,
  `services/stock.py`, unas 400 líneas con la transferencia, el historial y la grilla por depósito) y tres pantallas propias
  (`Sucursales`, `Stock`, `Transferencias`, ~700 líneas). Contalibra usa `build_depositos_router` y `build_stock_router` de
  `libracommerce` y las pantallas `Depositos`/`DepositoDetalle`/`DepositoTransferencia`/`Stock` del kit. Medido antes de empezar:
  las factories leen `locations`, `stock_movements` y `catalog_items`, **las mismas tablas** que VentaLibra: no hay migración.
- Decisión: adoptar los routers y las pantallas y expresar lo propio como **variantes** (el motor es la referencia).
  - `libracommerce` v0.18.0: `OpcionesDepositos` (`autorizar_escritura`, `validar_alta`, `validar_edicion`,
    `validar_eliminacion`, `al_guardar`), el `tipo` del depósito, `GET /api/depositos/transferencias` (el historial), el resultado
    de cada lado en la transferencia, `OpcionesStock.por_deposito` (columnas por depósito y ajuste a un depósito) y el ajuste, la
    lectura y la transferencia **por depósito y por variante**.
  - `libra-ui` v0.78.0: `Depositos` con `tipos`, `soloLectura`, `titulo`; `DepositoDetalle` con `soloLectura`;
    `DepositoTransferencia` con `conHistorial`; `Stock` con columnas y ajuste por depósito (dirigido por los datos) y `conFiltros`.
  - VentaLibra declara sus reglas en `app/depositos_ganchos.py` y **retira `/locations`, `/stock` y las tres pantallas**.
- Reglas propias que quedan como ganchos: dos tipos (`store`/`warehouse`) que no se cambian; como mínimo una sucursal y un depósito
  activos; una sucursal con turno abierto no se desactiva; una sucursal no se elimina (tiene cajas y ventas); la sucursal nueva recibe su
  caja; alta, edición, predeterminada y baja son de admin, la lectura y la transferencia de staff y admin.
- Consecuencias:
  - Los consumidores del POS pasan a `GET /api/depositos` (`nombre`, `tipo`, `activo`, `es_default`; 1/0 en los dos últimos): POS,
    devolución, compras, cierre diario y cajas.
  - `PUT` de un depósito ya no recibe el tipo ni `is_default`: el tipo se elige al crear y la predeterminada se marca con
    `POST /api/depositos/{id}/set-default`. Las guardas de default son las del motor y contestan **422** (antes 409).
  - Un depósito inexistente o inactivo en una transferencia es **422** (antes 404). Sin `variant_id`, el stock de un ítem en un depósito
    es el de **todas sus variantes** (antes sólo lo cargado sin variante); con `variant_id`, el de esa variante.
  - **Se pierde el tipo «viejo» retipable** (una fila con un tipo que no era ninguno de los dos podía elegirse una vez): el `PUT` del
    motor no trae el tipo. Un dato así se corrige en la base (se hizo con dev el 2026-09-26).
  - `GET /api/productos` se monta **de sólo lectura** (405 en escrituras) porque las pantallas del kit de transferencia listan productos de
    ahí; se edita por `/catalog` hasta la fase 7, que adopta la pantalla de Productos y retira esa API.
  - La pantalla de Stock gana lo que Contalibra ya tenía: alertas de mínimo, ajuste (fijar, entrada, salida) con fecha y
    referencia, y el historial de movimientos; conserva el buscador y «sólo los que tienen stock» que tenía la propia.
  - **Auditoría:** un ajuste de stock y la edición de una sucursal o depósito ya no quedan en `actividad_log` (el router
    del motor escribe sin el repositorio envuelto; tampoco pasa en Contalibra). El ajuste sí queda en el ledger
    (`stock_movements`, con `created_by`) y en el historial de movimientos. **Deuda** (resuelta en la fase 7, ADR-034: la fábrica del repositorio devolvió la auditoría de ubicaciones y productos; el ajuste de stock sigue sin quedar en los Logs).
  - Para las pantallas del kit el frontend suma `components/ui/textarea` y `formatEntero` (lo que cada producto provee).
- Depende de: `libracommerce` v0.18.0 y `libra-ui` v0.78.0 publicados y los pines de este repo subidos.

## ADR-034 — Productos y listas de precio con los routers del motor y las pantallas del kit (fase 7 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-27
- Contexto: VentaLibra tenía `/catalog` (`app/routers/catalog.py` 334 líneas, `services/catalog.py` 395: productos, códigos,
  variantes, escaneo, unidades y categorías), `/pricing` (119 + 56, que **ninguna pantalla usaba**) y la pantalla propia de Productos
  (623 líneas). Contalibra usa `build_productos_router` y `build_listas_precio_router` de `libracommerce` y las pantallas `Productos`,
  `ListasPrecio` y `ListaPrecioDetalle` del kit. Las factories leen las mismas tablas: sin migración de datos.
- Decisión: adoptar los routers y las pantallas y expresar lo propio como **variantes**.
  - `libracommerce` v0.19.0: `OpcionesCatalogo` (`unidades_de_la_base`, `autorizar_categorias`, `validar_producto`,
    `validar_eliminacion`); `GET`/`POST /api/productos/{id}/codigos` (varios códigos por producto); `categoria_id` en el producto; el
    listado con `solo_activos`/`solo_vendibles` y **búsqueda sin acentos y por todas las palabras**; y **la fábrica del repositorio**
    (`usar_fabrica_de_repositorio`): el ERP arma su repositorio con la que declara el producto.
  - `libra-ui` v0.79.0: `Productos` con `conDetalle` (códigos y variantes), `conStockTotal`, `conEliminar` y las unidades del backend.
  - VentaLibra declara sus reglas en `app/productos_ganchos.py`, monta las listas de precio (CRUD, quiebres por cantidad y precios con
    vigencia y por sucursal; **de admin**) y **retira `/catalog/items*`, `/pricing`, sus servicios y la pantalla propia**.
- Se queda en VentaLibra a propósito (🔷): `/catalog/units` (código, nombre, si admite fracciones, escala decimal) y
  `/catalog/categories` (jerárquicas, con baja lógica y nombre único entre las activas). El motor no las tiene; el alta y la baja de
  categorías del motor están **cerradas** (405) para que no haya dos vías.
- Consecuencias:
  - **Se arreglaron cosas del motor que habrían roto los datos de VentaLibra:** guardar un producto reescribía su unidad (nombre
    `Kilogramo`→`kg`, escala 3→0), reseteaba `purchasable`/`tax_profile`/`metadata` y le cambiaba el tipo al código principal.
  - **La auditoría vuelve** (deuda de la fase 6): con la fábrica, el alta y la edición de productos, códigos, variantes y ubicaciones quedan
    en `actividad_log` como antes. El ajuste de stock sigue sin quedar (es SQL directo; sí queda en el ledger).
  - El POS y Compras usan `/api/productos` (`nombre`, `precio_venta` numérico, `unidad`, `activo`): el POS pide `solo_activos=true`; el
    escaneo es `GET /api/productos/escanear` (`producto`, `cantidad`, `precio_unitario`, `de_balanza`).
  - La unidad tiene que existir (422; el motor la crearía al pasar) y se bloquea con movimientos (409); la categoría tiene que existir y estar
    activa (422); el tipo (producto/servicio) no se cambia (409); un producto **no se elimina** (409), se desactiva.
  - **Se pierde la lista predeterminada** (`is_default`, con su 409 si había dos y `resolve` sin lista): nadie la usaba y el motor no la tiene.
  - Sí se pierde `purchasable` como dato editable (sólo viajaba de ida y vuelta; se conserva lo que ya había).
  - La búsqueda por nombre gana el código y la categoría (y la sigue sin distinguir acentos ni mayúsculas).
  - El frontend suma `components/ui/radio-group` (lo que el kit espera del producto).
- Depende de: `libracommerce` v0.19.0 y `libra-ui` v0.79.0 publicados y los pines de este repo subidos.

## ADR-035 — Reportes con el router del motor y las pantallas del kit (fase 8 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-27
- Contexto: VentaLibra tenía `/reports/{sales,caja,stock}` (`app/routers/reports.py` 27 líneas + `services/reports.py` 129) y una pantalla
  propia de Reportes (188). Contalibra usa `build_reportes_router` (`libracore`) sobre `libracommerce.erp.reportes` y las pantallas
  `Reportes` y `CajaMedios` del kit.
- Decisión: adoptar el router y las pantallas, sin variantes de pantalla (el kit no cambió). Las diferencias de VentaLibra son de **datos** y
  entran como opciones del motor con default = Contalibra:
  - `libracommerce` v0.20.0: `puerto_de_reportes(solo_confirmadas=)`: una venta **anulada** (`cancelled`) o **pendiente de cobro**
    (`draft`, un QR sin acreditar) no es una venta. Arreglo de paso: el saldo de caja del resumen no excluía los movimientos anulados.
  - `libracore` v1.113.0: `sin_fiado` en `build_reportes_router`, `build_reportes_export_router` y `db.reportes`: los reportes de caja dejan afuera
    la cuenta corriente. **Fiar no es cobrar:** la capa ERP escribe un movimiento de caja por cada medio, cuenta corriente incluido, y sin esto el
    reporte sumaba la deuda como ingreso y no coincidía con el arqueo del turno (ADR-027) ni con `get_caja_resumen`.
  - VentaLibra monta los dos con las dos opciones activas, sólo admin (como antes), y **retira `/reports/*`** y su servicio.
- Consecuencias:
  - **Se midió por mutación** que los defectos existían: sin las opciones, una venta anulada contaba y un pago a cuenta corriente entraba a la caja.
    **Contalibra y Restolibra tienen el mismo defecto por default**; no se cambió porque altera números que hoy ven sus usuarios (activarlo es pasar las dos
    opciones al montar).
  - La pantalla gana lo que Contalibra ya tenía: agrupación por día/semana/mes, medios de pago, exports CSV, facturas emitidas y la **Caja por medio**
    (por mostrador y por medio de cobro; nueva entrada de menú, sólo admin), que con varias cajas por sucursal es la pregunta natural.
  - `stock_bajo` son los productos por debajo de **su mínimo** (el que se carga en Productos), no un umbral global en cero; el listado completo de stock está
    en la pantalla de Stock.
  - Los tops de productos suman `cantidad × precio` (antes también descuento e impuestos, por ítem); los medios de pago de las ventas a cuenta corriente sí
    aparecen (la venta fue a cuenta corriente), pero no en la caja.
- Depende de: `libracommerce` v0.20.0 y `libracore` v1.113.0 publicados y los pines de este repo subidos. `libra-ui` no cambia.

## ADR-036 — Compras (órdenes y recepciones) pasa al motor y al kit (fase 9 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-27
- Contexto: VentaLibra tenía `/purchase-orders`/`/purchase-receipts` propios (`app/routers/purchasing.py` 218 líneas +
  `services/purchasing.py` 131) y las pantallas `Compras`/`CompraDetalle` (206 + 559). Es el caso inverso a las fases 1–8: acá **no
  hay** un "cómo lo monta Contalibra" que adoptar — VentaLibra es el único producto de la familia con seguimiento de pedido/recibido
  y movimiento de stock por compra (Contalibra y Restolibra resuelven "comprarle a un proveedor" con Egresos, sin eso). El dominio, el
  caso de uso (`confirm_purchase_receipt`) y las tablas ya vivían en `libracommerce` sin que ningún router los usara.
- Decisión: extraer el router y las pantallas TAL CUAL las tenía VentaLibra, en vez de adoptar algo ya existente:
  - `libracommerce` v0.21.0: `build_compras_router` (`libracommerce.web.compras_router`), con el dominio en inglés (`number`,
    `status`, `quantity_ordered`...) como ya estaba — no hay una forma "de Contalibra" en español a la que converger. Sólo
    `proveedor_id` (nunca `supplier_party_id`) es parte del contrato público, y `OpcionesCompras` agrega, sin cambiar el default
    (`proveedor_id == party_id`, sin restricción de quién escribe): `numerador`, y el par `resolver_proveedor`/`proveedor_de` para
    que un producto traduzca su propio esquema de ids de proveedor. Nuevo respecto de lo que tenía VentaLibra: filtro server-side de
    recepciones por `purchase_order_id` (antes sólo del lado del cliente) y prefijo `/api` (antes no lo tenía).
  - `libra-ui` v0.80.0: `comercio/Compras` y `comercio/CompraDetalle`, extraídas casi verbatim (mismos textos, mismo flujo de
    "Recibir mercadería" dentro de la orden) — sólo cambian las rutas a `/api/...` y `location_id` por `deposito_id` en la
    confirmación, más los tipos (`PurchaseOrder`, `PurchaseReceipt`...) que pasan a `comercio/tipos`.
  - VentaLibra monta `build_compras_router` con `app/compras_ganchos.py` (numeración con `next_sequence`, atómica — el `MAX(id)+1`
    sin lock del motor es para baja concurrencia; y la traducción de `proveedor_id` reusando `app/services/proveedores.py`, que ya
    existía desde la fase 1), bajo `dependencies=staff_or_admin` como el router anterior (`autorizar_escritura` no hace falta:
    lectura y escritura quedan igual de protegidas). Retira `/purchase-orders`/`/purchase-receipts` propios.
- Consecuencias:
  - El contrato público deja de exponer `supplier_party_id` (sólo lo tenía por comodidad de depuración; ninguna pantalla lo leía).
  - `GET /api/purchase-receipts?purchase_order_id=` ya no depende de traer todas las recepciones y filtrar en el cliente.
  - Contalibra y Restolibra no ganan nada de esto (no tienen el módulo) ni pierden nada (Egresos sigue disponible para los dos).
- Depende de: `libracommerce` v0.21.0 y `libra-ui` v0.80.0 publicados y los pines de este repo subidos.

## ADR-037 — Tesorería con el router del motor, libre en todos los planes (fase 10 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-27
- Contexto: VentaLibra no tenía ninguna forma de llevar cuentas bancarias, efectivo en caja fuerte o billeteras
  digitales aparte de la caja del POS. `libracore.tesoreria_router.build_tesoreria_router` y las pantallas
  `comercio/Tesoreria`/`TesoreriaDetalle` del kit ya existen, sin ganchos ni variantes: cuentas, movimientos y
  transferencias son un problema de cualquier comercio, no del modelo de venta de este producto. La tabla
  (`cuentas_tesoreria`/`movimientos_tesoreria`) ya vive en la cadena de migraciones de `libracore` que VentaLibra
  corre en cada deploy, vacía hasta ahora: sin riesgo de dato.
- Decisión: montar `build_tesoreria_router` tal cual, sin `app/*_ganchos.py` (no hace falta: el router no tiene
  opciones). Único punto que decidir era **quién la ve**: en Contalibra, `tesoreria` es un módulo real de
  `plans.py` (gateado, plan "estándar"). Se le preguntó al humano y decidió que en VentaLibra queda **libre en
  todos los planes**, como Compras, Ventas o Caja — coherente con el propio `plans.py` de este producto
  ("facturación es el único módulo gateable por ahora"). De admin (mismo criterio que Cajas y Listas de precio):
  cuentas y transferencias de plata no son una tarea de mostrador.
- Consecuencias:
  - VentaLibra no agrega `"tesoreria"` a `PLAN_MODULOS`: no hay `require_module` en el montaje.
  - Nueva entrada de menú "Tesorería" (icono `Banknote`: `Landmark` ya lo usa "Cajas" en este producto).
  - Contalibra y Restolibra no se tocan: siguen con `tesoreria` como módulo de plan "estándar".
- Depende de: nada nuevo que publicar — `libracore` y `libra-ui` ya traían el router y las pantallas sin cambios.

## ADR-038 — Egresos y Libros IVA con los routers del motor, en una sola tanda (fases 11 y 12 de la adopción)

- Estado: aceptada
- Fecha: 2026-09-27
- Contexto: VentaLibra no tenía forma de registrar un gasto que no fuera mercadería (alquiler, sueldos,
  servicios) ni el comprobante fiscal de un pago a un proveedor — Compras (fase 9) repone inventario,
  no lleva contabilidad del pago. Tampoco tenía libro IVA: el lado ventas ya funciona solo (VentaLibra
  factura contra la tabla `facturas` del motor desde `venta_facturacion`), pero el lado compras necesita
  `egresos`, vacía hasta esta fase. El humano pidió las dos fases en una sola tanda porque Libros IVA
  depende de que Egresos tenga uso real.
  `libracore.egresos_router.build_egresos_router`/`build_libros_iva_router`/`build_libros_iva_export_router`
  y las pantallas `comercio/Egresos`/`EgresoDetalle`/`LibrosIva` ya existen, sin ganchos ni variantes —
  mismo caso que Tesorería.
- Decisión: montar los tres routers tal cual.
  - **Egresos**: de staff y admin (como Compras y Proveedores en este producto; en Contalibra también es
    de cualquier usuario autenticado, no sólo admin) — es una tarea operativa, no de configuración. Libre
    en todos los planes (mismo criterio que Tesorería, sin volver a preguntar la misma política de
    negocio). Pagar un egreso escribe un movimiento en `libracore.db.caja` sin `turno_id`: se investigó
    si eso rompía el arqueo de un turno y no es así — `cerrar_turno` calcula el monto esperado sólo con
    `efectivo_ventas` (las ventas atadas al turno), nunca lee `caja_movimientos` en general; y el resumen
    de caja (`get_caja_resumen`, el que alimenta a Reportes y Caja por medio) filtra por `caja_id` y
    fecha, no por turno. Contalibra tiene el mismo comportamiento.
  - **Libros IVA**: de admin, como en Contalibra — es un reporte contable-fiscal, no una tarea de
    mostrador. Los cuatro exports REGINFO (`build_libros_iva_export_router`) van fuera de `/api` (piden
    la cookie de sesión directo, son un `<a href>` de descarga): `vite.config.ts` los suma a
    `RUTAS_PROPIAS_DEL_BACKEND` con un patrón angosto (`/libros-iva/export/*`), no al `API_PATHS` por
    prefijo, porque `/libros-iva` a secas es la pantalla del kit — misma colisión que ya documentaba el
    archivo para `/ventas` y `/pos` (F4, ADR-025).
  - Ninguno de los dos se agrega a `PLAN_MODULOS`: libres en todos los planes.
- Consecuencias:
  - La guarda de baja de un proveedor (`app/proveedores_guarda.py`) queda con **dos** protecciones que se
    complementan: la propia del motor contra egresos (`ValueError` → 422, recién activa: antes de esta
    fase VentaLibra no tenía egresos) y la de este producto contra compras (409, sin cambios).
  - Nueva entrada de menú "Egresos" (icono `HandCoins`, staff y admin) y "Libros IVA" (icono `BookText`,
    admin) — íconos elegidos porque los de Contalibra (`ShoppingBag`, ya usado por "Compras") chocaban.
  - Contalibra y Restolibra no se tocan: siguen con `egresos`/`libros_iva` como módulos de plan.
- Depende de: nada nuevo que publicar — `libracore` y `libra-ui` ya traían los routers y las pantallas
  sin cambios.

## ADR-039 — Dashboard con el router del motor y la pantalla del kit, gateado a premium (fase 13 de la adopción)

- Estado: aceptada; **el gate a Premium se retiró en ADR-048**: el dashboard es libre en los dos planes.
- Fecha: 2026-09-27
- Contexto: a diferencia de Tesorería/Egresos/Libros IVA (fases 10–12), acá **sí hubo que construir**:
  `libracore.dashboard_router.build_dashboard_router` no tenía `sin_fiado` (el mismo problema que Reportes
  tenía antes de la fase 8: sin él, "Cobrado del mes" y "Saldo de caja" cuentan una venta a cuenta
  corriente como plata ya entrada) — se agregó en `libracore` v1.114.0. Y la pantalla `Dashboard` no
  existía en el kit: es la primera del inventario que sólo tenía referencia en **Contalibra**
  (`pages/Dashboard.tsx`); Restolibra redirige `/dashboard` a `/salon` sin llegar a renderizarla. Se
  extrajo a `libra-ui` v0.81.0 con props aditivas para lo que Contalibra tiene y otro producto no
  (`accionesRapidas`, `conPresupuestos`, `rutaDeFactura`/`rutaDeFacturas`/`rutaDeCaja` nullables — mismo
  patrón que `rutaDeFactura` de `Ventas`, ya `null` en este producto).
- Decisión: a diferencia de las tres fases anteriores, acá el propio `plans.py` de este producto **ya
  anticipaba el gate**, desde antes de que el módulo existiera: *"Facturación es el único módulo gateable
  por ahora; Premium queda con margen para dashboard/reportes cuando se construyan"* (el comentario original
  del ROADMAP). No fue necesario volver a preguntar la política: se agrega `"dashboard"` a `_PREMIUM`.
  Contalibra, para comparar, monta el router **sin ningún gate** (ni admin ni módulo) — acá se lo dejó de
  admin de todos modos, mismo criterio que Reportes y Caja por medio en este producto.
  VentaLibra pasa `accionesRapidas=[]` (no tiene facturas/presupuestos/remitos como documentos propios,
  ni una pantalla de "nuevo movimiento de caja" suelta), `conPresupuestos={false}` y las tres rutas en
  `null` (no hay pantalla de facturas ni una de caja general).
- Consecuencias:
  - Nueva entrada de menú "Dashboard" (icono `LayoutDashboard`), visible para cualquier admin **aunque el
    plan no lo incluya**: sin nav-hiding por módulo (no hay ese mecanismo armado en este producto todavía),
    un admin de plan básico o estándar que hace clic ve el 403 genérico del motor
    (`"modulo 'dashboard' no incluido en el plan actual"`), mismo comportamiento ya establecido para el
    add-on `resguardo_externo`.
  - Contalibra y Restolibra no se tocan: Contalibra sigue sin ningún gate en su propio Dashboard.
- Depende de: `libracore` v1.114.0 y `libra-ui` v0.81.0 publicados y los pines de este repo subidos.

## ADR-040 — Recibos y consulta de CUIT como factories del motor (fase 14, cierra la adopción de motores)

- Estado: aceptada
- Fecha: 2026-09-28
- Contexto: el último ítem 🟡 de deuda técnica del inventario de adopción de motores (no un módulo de
  negocio nuevo, a diferencia de las fases 1–13): `app/routers/recibos.py` de este producto (dos rutas,
  las que llaman las pantallas de cuenta corriente del kit) y el mismo router de Contalibra/Restolibra
  eran ~130 líneas de código idéntico en cada repo, y `/api/consultar-cuit/{cuit}` (~70 líneas más) era
  código propio de Contalibra desde siempre, con el cliente WSAA/WSPadron ya en el motor
  (`libracore.arca_wsaa`/`arca_wspadron`) pero sin el endpoint. Se extrajeron los dos a `libracore` v1.115.0:
  `recibos_router.build_recibos_router(usuario_actual, solo_admin, get_venta=None)` y
  `consultar_cuit_router.build_consultar_cuit_router(usuario_actual)`.
- Decisión: se montan los dos routers completos del motor, sin apagar nada — a diferencia de Tesorería/
  Egresos/Libros IVA (fases sin ganchos porque ya encajaban), acá el único gancho real es `get_venta`
  (`app.db_ventas.get_venta`, ya usado en el resto del producto): las ventas de mostrador de VentaLibra
  viven en `sales` de LibraCommerce, no en `ventas` del propio esquema del motor.
  `emitir_recibo_factura`/`emitir_recibo_cobranza` no necesitan ningún gancho: ya resuelven contra tablas
  que este producto comparte con Contalibra desde fases anteriores (`facturas`, `caja_movimientos`,
  `clients`, `cc_pagos`). `conConsultaCuit` de `Clientes`/`ClienteDetalle` (kit, ya existía desde la fase 2)
  pasa a su default (`true`): el motor ya tiene el endpoint que necesitaba.
- Consecuencias:
  - VentaLibra gana, sin haberlo pedido, lo que antes sólo tenía Contalibra: listar y ver el detalle de
    los recibos emitidos, emitir el recibo de una venta de mostrador (`POST /api/recibos/venta/{id}`) y
    anular un recibo (sólo admin, `solo_admin`) — mismo criterio que toda la adopción: la diferencia por
    defecto es la de Contalibra, no la que este producto tenía escrita a mano.
  - **Cambio de comportamiento:** un `cc_pago_id`/`factura_id`/`venta_id` sin cobros para emitir contestaba
    **404** en el router propio y contesta **409** con el del motor (mismo criterio que Contalibra:
    `SinCobros` es un conflicto de estado, no un recurso inexistente). Avisado antes de publicar.
  - `app/routers/recibos.py` se retira (las dos rutas que tenía ya las cubre el router del motor).
  - Contalibra y Restolibra no se tocan: siguen con su propio router de recibos y su propio endpoint de
    consulta de CUIT hasta que alguien los migre a esta factory (fuera del alcance de esta fase).
- Depende de: `libracore` v1.115.0 publicado y el pin de este repo subido.

## ADR-041 — Actualización masiva de precios desde la planilla de un proveedor

- Estado: aceptada
- Fecha: 2026-09-28
- Contexto: primer ítem del roadmap de producto (no una adopción de motores: no existía en ningún
  producto de la familia — ver `wiki/analyses/ventalibra-gaps-despensa.md`, "Importantes, no
  bloqueantes"). Con la inflación argentina, cargar precios a mano contra la lista de un proveedor
  es inviable. Se construyó en `libracommerce` (donde ya vive el catálogo de este producto desde la
  fase 7) en vez de en este repo, para que Contalibra/Restolibra puedan adoptarla el día de mañana.
  Dos decisiones de negocio consultadas al humano: qué actualiza la planilla (costo solo, con la
  venta recalculada manteniendo el margen actual — no todos los proveedores mandan un precio de
  venta sugerido) y con qué dato matchea cada fila (código de barra, ya cargado en cada producto).
- Decisión: se monta `libracommerce.web.planillas_router.build_actualizacion_precios_router` tal
  cual (sin ganchos: `get_venta`-style no aplica acá, el matcheo es genérico por `item_codes`), de
  admin (`/actualizacion-masiva-precios`, mismo criterio que Listas de precio). El extra
  `[planillas]` (trae `openpyxl`) se suma al pin de `libracommerce` de este producto.
- Consecuencias: sube un `.xlsx`, ve la vista previa (costo/venta antes → después, códigos sin
  producto aparte) y aplica — los dos pasos mandan la misma planilla, nunca un precio ya calculado.
  Un producto sin costo previo (`precio_costo=0`) no tiene margen del que partir: se le actualiza el
  costo pero la venta queda igual, marcado en la pantalla. Contalibra y Restolibra no se tocan.
- Depende de: `libracommerce` (PR #101, extra `[planillas]`) y `libra-ui` v0.82.0 (`comercio/
  ActualizacionMasivaPrecios`, PR #204) publicados y los pines de este repo subidos.

## ADR-042 — Promociones por cantidad y vigencia: el POS cobra al precio de la lista predeterminada

- Estado: aceptada
- Fecha: 2026-09-28
- Contexto: roadmap de producto, "promociones y combos". El motor ya resolvía precios por cantidad y
  por fecha/hora (`resolve_price`, quiebres y vigencias en `item_prices`), pero nada del producto lo
  usaba: el POS vendía siempre a `precio_venta`, ni siquiera `Ventas.tsx` de Contalibra los aplicaba, y
  no había forma de marcar una lista como predeterminada (`resolve_price` sin lista cae en la
  `is_default=1 AND active=1`, capacidad muerta hasta hoy). El humano eligió construir cantidad y
  vigencia juntas. Alcance de esta tanda: promociones de un producto; los combos (varios productos por
  un precio) siguen pendientes.
- Decisión: el motor suma `set_lista_precio_default` y `delete_precio_vigente` (`libracommerce`
  v0.24.0, ADR-011) y el kit el botón de predeterminar y el editor de promociones (`libra-ui` v0.83.0,
  `conVigencias`), que este producto activa en el detalle de la lista. El POS carga la lista
  predeterminada al abrir y consulta `GET /api/listas-precio/{id}/precio?producto_id&cantidad&en` al
  agregar una línea y al confirmar un cambio de cantidad. Cualquier falla (sin lista predeterminada,
  sin precio para el producto, error de red) cae al precio plano sin bloquear la venta, criterio de
  `mp-estado`. Un precio de etiqueta de balanza no se pisa.
- Consecuencias: ADR-025 D1 (carrito local, sin ida y vuelta por edición) se respeta con matiz: el
  precio se resuelve al agregar (`elegirItem` ya era asíncrono por las variantes) y al confirmar la
  cantidad con «Aceptar» (acción discreta, no por tecla); la cantidad se carga al instante y el precio
  se refresca después. Una instalación sin lista predeterminada vende exactamente como antes. Queda
  fuera la ruta de variantes (`elegirVariante`), que sigue al precio plano.
- Depende de: `libracommerce` v0.24.0 (PR #107) y `libra-ui` v0.83.0 (PR #205), ya publicados.

## ADR-043 — Promociones «llevá N pagá M» y combos: el servidor las aplica y el POS las muestra

- Estado: aceptada
- Fecha: 2026-09-28
- Contexto: segundo ítem del roadmap de producto, que ADR-042 dejó a medias (precio por cantidad y
  vigencia sí; combos y 2x1 no). Es construcción nueva: ningún producto de la familia tenía
  promociones por regla, así que se hizo en `libracommerce` (ADR-014) para que Contalibra y
  Restolibra puedan montarlas. Dos decisiones de negocio consultadas al humano: construir «llevá N
  pagá M» y combos fijos juntos, y registrar la promoción como **descuento de la venta más una
  tabla que anota cuál se aplicó** (no repartir el ahorro en el precio de cada línea, que
  distorsionaría el precio por producto en reportes y devoluciones).
- Decisión: se montan `build_promociones_router` (las reglas, **admin**) y
  `build_promociones_calculo_router` (`POST /api/promociones/calcular`, sólo lee, **staff o admin**),
  y `OpcionesVentas(promociones=True)`. El servidor es la autoridad: `POST /api/ventas` calcula las
  promociones con las líneas que llegan, suma el ahorro al `descuento` (con tope en el subtotal) y
  lo registra en `sale_promotions`, todo en la transacción de la venta. Migración `0006_promociones`
  (`erp.schema.crear_promociones`, la misma función que `configure()`). La pantalla es la del kit
  sin wrapper (`libra-ui/comercio/Promociones`), ruta y menú de admin.
- El POS consulta `calcular` después de cada cambio del carrito (agregar, cantidad, quitar: acciones
  discretas, no teclas, así que ADR-025 D1 se respeta) y muestra subtotal, cada promoción y el total
  con el ahorro, que es lo que se cobra: el mismo que el servidor va a registrar. **`Cobrar` espera
  el cálculo** para no abrir el cobro con un total viejo. Si el cálculo falla se vende sin descuento
  en pantalla, sin bloquear; el total que manda es el del servidor (la respuesta trae `descuento` y
  `promociones`), y una venta cobrada de más no queda rechazada por `exigir_pago_completo`.
- 🔴 **Arreglo que viaja con esto: el cajero no podía leer el precio de la lista.** El cableado de
  ADR-042 pide `GET /api/listas-precio/{id}/precio` desde el POS, y esa ruta vive en el router de
  quiebres, que es de admin: un cajero recibía 403 y el POS caía al precio plano **en silencio**
  (los tests con `fetch` simulado no lo podían ver; sólo el admin tenía el precio de lista). La
  guarda `require_staff_precio_admin_resto` (`app/auth.py`) abre **sólo** ese `GET` a staff. Los
  quiebres en sí y todo lo que escribe siguen siendo de admin, como fijó #350.
- 🔴 **Segundo arreglo: la vigencia se comparaba en UTC.** El POS manda `en` con `toISOString()` y
  el motor lo comparaba como texto contra vigencias guardadas en hora local: una promoción de 18 a
  20 hs se activaba a las 15 en Argentina. `libracommerce` v0.25.0 pasa un instante con zona a hora
  local antes de comparar (ADR-014 del motor); el POS no cambia.
- Consecuencias: las promociones con horario rigen en hora de Argentina. Una instalación sin
  promociones vende exactamente como antes. Quedan fuera la ruta de variantes del POS
  (`elegirVariante`, que sigue al precio plano y sin promociones sobre la variante) y mostrar las
  promociones aplicadas en el detalle de la venta y en el ticket.
- Depende de: `libracommerce` v0.25.0 (ADR-014) y `libra-ui` v0.84.0 (`comercio/Promociones`)
  publicados y los pines de este repo subidos.

## ADR-044 — Sucursal y depósito son entidades distintas: el stock vive sólo en el depósito

- Estado: aceptada (decisión del humano, 2026-09-28); reemplaza los dos tipos `store`/`warehouse` de ADR-033
- Fecha: 2026-09-28
- Contexto: desde ADR-033 una sucursal y un depósito eran la misma fila de `locations`, distinguidas por
  `location_type`, y cualquiera de las dos podía tener stock. Al entrar a Sucursales el humano esperaba lo
  contrario: que el stock viva sólo en el depósito, que toda sucursal tenga al menos uno y que pueda tener varios.
  LibraDesk ya tenía esa jerarquía en su capa de producto; se subió al motor (`libracommerce` ADR-012 y ADR-013) para que
  la reciban todos los consumidores en vez de portarla cada uno.
- Decisión: una sucursal es una fila de `branches` y sus depósitos son `locations` con `branch_id`. El motor impone que toda
  sucursal tenga un depósito activo, que uno sea el de venta (`deposito_predeterminado_id`), que no se desactive ni se
  elimine el último y que la baja de una sucursal exija que no queden existencias. Aquí quedan como ganchos: todo
  depósito pertenece a una sucursal; la última sucursal activa y una con turno abierto no se desactivan; la sucursal nueva
  recibe su primera caja. La venta y la devolución tienen que mover stock de un depósito de la **sucursal de la caja**
  del turno (`validar_deposito`), y el POS manda el depósito de venta de la sucursal elegida. `location_type` queda sin uso.
  - **La migración conserva los ids** (`app/sucursales_migracion.py`, revisión `0006`, y `db.connect()` en cada arranque y al
    restaurar un respaldo viejo): cada `store` pasa a ser la sucursal con su mismo id y su fila queda como su depósito, así
    que `cajas.sucursal_id`, los turnos, los precios por sucursal y el stock no se reescriben ni se transfiere nada. Los
    depósitos sin dueño van a la sucursal predeterminada, o a la que diga `VENTALIBRA_DEPOSITOS_A_SUCURSAL="2:1,5:3"`; las
    cajas de un depósito pasan a la sucursal de ese depósito. `scripts/preflight_jerarquia.py` audita antes, de sólo lectura.
- Consecuencias: los cierres diarios de un depósito (posibles hasta el 2026-09-25, cuando cualquier ubicación tenía cajas) no
  se reasignan porque su numeración es única por sucursal: quedan como estaban y el preflight los cuenta. La migración no
  se revierte con datos (el `downgrade` es de mejor esfuerzo): el camino de vuelta es el respaldo previo al deploy. Backend
  y frontend salen juntos: la API de sucursales cambia y el POS depende de ella.
- Depende de: `libracommerce` v0.25.0 o posterior (PR #106 y #109; el pin de este repo ya está en v0.25.1) y `libra-ui` v0.85.0
  (`comercio/Sucursales` y `SucursalDetalle`, PR #207), ambos publicados.

## ADR-045 — Las promociones aplicadas se ven en el detalle de la venta, el ticket y el comprobante del POS

- Estado: aceptada
- Fecha: 2026-09-29
- Contexto: ADR-043 dejó las promociones aplicándose y registradas (`sale_promotions`), pero invisibles: el
  cliente veía un `Descuento` sin saber de qué era, en el ticket y en la pantalla. `GET /api/ventas/{id}` y
  la respuesta de `POST /api/ventas` ya traían `promociones`; faltaba mostrarlas.
- Decisión: tres lugares, cada uno con su cambio en el repo que corresponde, todos aditivos. El detalle de
  venta (`libra-ui`, `VentaDetalle`) muestra una fila por promoción y deja «Descuento» para el resto. El
  ticket impreso (`libracore.ticket_generator`, ADR-012 de libracore) imprime una fila por promoción; el
  puente de este producto (`app/services/tickets.py`, `GET /ventas/{id}/ticket`) lee `sale_promotions` de
  ESA venta y se la pasa. El comprobante de «venta cobrada» del POS lista cada promoción con su ahorro.
- **El `descuento` de la venta ya incluye el ahorro de las promociones**, así que en el detalle y en el
  ticket la fila «Descuento» muestra sólo lo que sobra (un descuento manual) y desaparece si no queda nada:
  el mismo monto no sale contado dos veces.
- Consecuencias: una venta anterior a las promociones, o sin ninguna aplicada, se ve y se imprime
  exactamente como antes; lo fijan tests en los tres repos. La venta cobrada por QR pendiente no trae las
  promociones hasta que se refresca (`GET /api/ventas/{id}`), como el resto de sus datos.
- Depende de: `libracore` con ADR-012 (`promociones` en `generar_ticket_venta`) y `libra-ui` v0.86.0
  (`VentaDetalle`), publicados y los pines de este repo subidos.


## ADR-046 — Margen y rotación: el router del motor y la pantalla del kit, sin gate de plan todavía

- Estado: aceptada; **el gate de plan queda sin decidir** (ver Consecuencias)
- Fecha: 2026-09-29
- Contexto: tanda 1 del roadmap de producto (`wiki/analyses/ventalibra-gaps-despensa.md`): "reportes de margen y rotación". Lo que ya
  había (`/api/reportes`, ADR-035) cuenta plata vendida por producto, no cuánto se ganó. Decisión vigente del humano: el motor es el
  origen, así que la agregación no se escribe acá.
- Decisión: VentaLibra sólo monta y prende. `libracommerce.web.margen_router.build_margen_router` (v0.26.0, ADR-015 del motor) cuelga
  de `/api/reportes/margen` con `conexion=lc_get_connection` y `admin_only`, y la pantalla es `libra-ui/comercio/Margen` (v0.87.0),
  montada por `frontend/src/pages/Margen.tsx` en `/margen` (admin). Sin adaptadores que espejen datos y sin parametrizar el kit. No hay
  migración: sólo lee `sales`, `sale_items`, `stock_movements` y `catalog_items`.
  - **Qué mide** (lo resuelve el motor, se prueba allá): una venta anulada o pendiente de cobro no cuenta; las devoluciones se restan
    del ledger de stock (la venta sigue `confirmed`); el descuento de la venta se reparte entre las líneas. **Fiar es vender**: a
    diferencia de la caja, aquí no hay `sin_fiado`.
  - **El costo es el de HOY, y la pantalla lo dice.** `POST /api/ventas` (`erp.ventas.crear_venta`) no guarda `sale_items.unit_cost_snapshot`,
    así que el motor usa el `default_cost` actual del producto y marca `costo_estimado`; un producto sin costo cargado sale marcado
    `sin_costo` (su margen figura 100 % y no es real). Un cambio de costo reescribe hacia atrás el margen de lo ya vendido hasta que la venta
    guarde su costo.
  - CSV bajo `/api/reportes/margen/export/*`: no hace falta sumar una ruta al proxy de Vite (`/api` ya está).
- Consecuencias: **pendiente de decisión del humano**: en qué plan cae el margen. `plans.py` anticipa "Premium con margen para reportes";
  no se asignó ninguno y hoy lo ve todo admin, igual que Reportes (`tests/test_margen.py::test_sin_decision_de_plan_esta_disponible_para_todo_admin`
  lo documenta). Para gatearlo: sumar `"margen"` al plan elegido en `plans.py` y `Depends(require_module("margen"))` en el `include_router` de
  `app/main.py`. Segundo pendiente, de motor: guardar el costo de la línea al vender (`crear_venta`), lo que vuelve exacto el margen de ahí en más.
- Depende de: `libracommerce` v0.26.0 y `libra-ui` v0.87.0; los pines de `pyproject.toml` y `frontend/package.json` se subieron en el mismo
  PR (#360).
- **Actualización 2026-09-29 (ADR-048):** el plan de Margen quedó decidido: **libre en Básico y en Premium**. No lleva `require_module`
  y `tests/test_margen.py::test_el_margen_esta_libre_en_todos_los_planes` lo fija. Sigue abierto el segundo pendiente (guardar el costo
  de la línea al vender).

## ADR-047 — Etiquetas de góndola: una pantalla del kit de sólo lectura, sin endpoint nuevo

- Estado: aceptada
- Fecha: 2026-09-29
- Contexto: roadmap de producto, «etiquetas de góndola» (`wiki/analyses/ventalibra-gaps-despensa.md`): al cambiar los
  precios hay que reimprimir el cartel de la góndola con el precio nuevo. Se midió antes de pedirle nada al motor: lo que
  ya expone alcanza —`GET /api/productos` trae nombre, código principal, precio y unidad; `/api/productos/categorias` el
  filtro; `/api/listas-precio` y `/api/listas-precio/{id}/items` el precio de cada lista—. Sin datos ni stock nuevos, sin
  migración.
- Decisión: la pantalla es del kit (`libra-ui/comercio/EtiquetasGondola`, decisión vigente: lo compartido va en el kit y
  el producto sólo lo monta, sin adaptadores) y se monta sin wrapper en `/etiquetas`, de admin como Listas de precio
  (`ProtectedRoute adminOnly` y `adminOnly: true` en el menú). No hay router ni ruta nueva en este repo. La etiqueta dice
  el precio que cobra el POS (ADR-042): el de la lista predeterminada, con el precio de venta del producto de respaldo.
  El código de barras se dibuja en SVG dentro del kit, sin dependencia: EAN-13 o EAN-8 si el código lo es y cierra, Code 128
  para el resto (el código interno `BEB-0001` que genera el alta no es un EAN).
- Consecuencias: 🔴 el precio impreso es el **base** de la lista: no resuelve quiebres por cantidad ni vigencias
  (promociones por fecha), que dependen de cuándo y cuánto se compre. Sale en una hoja A4 recortable (2, 3 o 4 columnas);
  una impresora de rollo (térmica) necesita el tamaño de papel de cada modelo y queda para una tanda aparte. **No se asignó
  a ningún plan** (`plans.py` sin tocar): la pantalla sólo lee endpoints que hoy son libres en todos los planes, así que un
  gate de verdad requeriría un endpoint propio; queda como decisión de negocio abierta.
- Depende de: `libra-ui` v0.88.0 (`comercio/EtiquetasGondola`) publicado y el pin de `frontend/package.json` subido de
  v0.85.0 a v0.88.0. Hasta entonces `App.tsx` no compila ni pasa el test nuevo.

## ADR-048 — Dos planes: Básico (un solo local) y Premium (facturación ARCA + multisucursal)

- Estado: aceptada (decisión del humano, 2026-09-29); reemplaza el esquema de planes de ADR-009, el gate de Dashboard de ADR-039 y
  la propuesta del PR #344 (rama `feature/planes-dos-niveles`), que queda superada
- Fecha: 2026-09-29
- Contexto: ADR-009 fijó tres planes diferenciados sólo por `facturacion`; ADR-039 le sumó `dashboard` a Premium y dejó a Estándar y
  Premium separados por un tablero. El PR #344 (2026-09-28) fusionaba Estándar en Premium dejando `facturacion` + `dashboard`, pero un
  tablero no es lo que separa a un comercio chico de uno grande. El humano lo redefinió el 2026-09-29: la diferencia sustancial es
  **lo fiscal y lo multisucursal**. (El PR #344 llamaba a su ADR «ADR-042», número que `develop` ya ocupa con otro tema —promociones—:
  no debe mergearse, y este ADR es el que queda.)
- Decisión: dos planes, precios los de #344.
  - **Básico ($20.000): un solo local** —una sucursal, con los depósitos que necesite—. Todo lo demás libre: POS, stock, compras, caja,
    clientes y proveedores, cuenta corriente, promociones, margen, dashboard, etiquetas, tesorería, egresos y libros IVA.
  - **Premium ($55.000)**: suma `facturacion` (ARCA) y el módulo nuevo `multisucursal` (más de una sucursal y la transferencia de
    mercadería entre sucursales).
  - `plans.py`: `PLANES = ["basico", "premium"]`, `_PREMIUM = _BASICO | {"facturacion", "multisucursal"}`, `TODOS_LOS_MODULOS` =
    esos dos. **`dashboard` deja de ser un módulo gateable**: se retira su `require_module` de `app/main.py`. Margen, Etiquetas, Tesorería,
    Egresos y Libros IVA ya eran libres y siguen igual.
- **El gate de «un solo local»** (`app/depositos_ganchos.py`, chequeo por request contra `app.state.modules`, como `require_module`):
  - **La unidad es la sucursal, no el depósito.** La jerarquía es sucursal → depósitos (ADR-044): un local con dos depósitos sigue siendo
    un local, así que agregar depósitos y transferir entre depósitos **de la misma sucursal** es libre en Básico.
  - Sin `multisucursal`: `POST /api/sucursales` da **403** si ya hay una sucursal activa (gancho `validar_alta`), y reactivar una
    sucursal dada de baja mientras hay otra activa también (`validar_edicion`); `POST /api/depositos/transferir` da **403** cuando el
    origen y el destino son de sucursales distintas. El mensaje sigue el de `require_module` («módulo 'multisucursal' no incluido en el
    plan actual») y agrega qué falta. El 403 nunca se dispara ante un cuerpo mal formado o un depósito inexistente: eso lo contesta el
    endpoint con su 422 de siempre.
  - **La transferencia es una dependencia del router de depósitos y no un gancho**, porque el motor (`libracommerce` v0.26.0) no tiene
    ninguno para ella: reconoce la ruta por su forma (`POST …/transferir`) y lee el cuerpo sólo en esa. Si el motor suma un gancho, se
    muda a él; un test falla si la ruta cambiara de nombre.
  - **No rompe lo que ya existe.** Una instalación con varias sucursales creadas antes (la demo tiene tres) en Básico sigue
    leyéndose, editándose, dando de baja y vendiendo: el gate sólo impide crear más, reactivar y cruzar mercadería. Nada se borra ni se
    oculta.
- **Lo que ya no existe, y las instancias que lo tienen guardado** (el estado vive en la tabla `modulos`: `modulo`, `habilitado`, `plan`;
  el gate lee sólo `habilitado`):
  - **Plan `estandar`** (`plans.PLANES_RETIRADOS = {"estandar": "premium"}`): se lo trata como Premium —tenía facturación y las
    sucursales eran libres, así que no pierde nada—, **con aviso**: `modulos_de_plan`, `aplicar_plan_en_db` y el arranque de la app
    dejan un `WARNING` en el log, y `aplicar_plan_en_db("estandar")` reescribe la etiqueta guardada a `premium`. Al 2026-09-29 sólo
    `demo` podía tenerlo. Antes de este cambio `modulos_de_plan("estandar")` habría dado un conjunto vacío y reaplicar ese plan habría
    apagado la facturación sin decirlo (la falla que dejaba abierta #344).
  - **Plan desconocido** (un typo): `aplicar_plan_en_db` levanta `ValueError` en vez de apagar todos los módulos de la instancia.
  - **Módulo `dashboard`**: la fila que quede en `modulos` no se borra ni se lee (`ModuleRepository.is_enabled` da `True` para todo
    módulo fuera de `TODOS_LOS_MODULOS`), aunque diga `habilitado=0`. `plans.MODULOS_RETIRADOS` lo deja escrito.
  - **Instancias ya desplegadas y el módulo nuevo**: `init_modules_schema` corre en cada arranque y sólo agrega lo que falta. Con «todo
    prendido» `multisucursal` habría quedado abierto en cada Básico existente hasta que alguien reaplicara el plan. Ahora, si las filas
    de plan dicen un solo plan conocido (los add-ons no cuentan), el módulo nuevo se siembra según ese plan: apagado en Básico,
    prendido en Premium y en `estandar`. Una base nueva, o con planes mezclados o desconocidos, se siembra como siempre.
- **La SPA** (`frontend/src/lib/modulos.ts`): `/auth/login` y `/auth/me` traen `modulos`, la lista de los módulos prendidos
  (`get_extras` de `libraauth`, mismo formato que LibraDesk). Si el campo falta —un backend viejo, o una falla al leerlo, en cuyo caso se
  omite y no se manda una lista vacía— la SPA ofrece todo y corta el 403 del backend. Con `multisucursal` apagado avisa «disponible en
  Premium» en Sucursales (arriba de la pantalla y en el botón de alta) y en Transferencias; con `facturacion` apagado, en la sección
  ARCA de Configuración (que no llama a `/config/arca`) y en el casillero «Emitir factura» del POS (apagado y sin marcar). El
  Dashboard no depende del plan.
- Consecuencias:
  - El alta de sucursal en Básico **no se puede apagar del todo en la pantalla**: el kit (`libra-ui/comercio/Sucursales`) no tiene una prop
    para esconder sólo ese botón —`soloLectura` esconde también la edición—, así que el botón sigue, dice «(Premium)» y el 403 del backend
    llega al formulario. Queda como pedido al kit (un `sinAlta`).
  - Transferencias no se esconde del menú en Básico: sirve entre los depósitos de la misma sucursal y muestra el historial.
  - **Acción de deploy**: reaplicar el plan a las instancias que corresponda no hace falta para que el gate funcione (el arranque siembra
    `multisucursal` según el plan guardado), pero **conviene reaplicar `premium` a `demo`** (`aplicar_plan_en_db`) para que su etiqueta
    deje de decir `estandar`. No verificado desde este repo: es una acción sobre una instancia corriendo.
  - `MercadoPago` sigue montando su configuración (`build_mp_config_router`) con `require_module("facturacion")`, un acoplamiento
    anterior a esta decisión: en Básico esa pantalla da 403. Queda como pendiente de decisión (el cobro por QR del POS no lo tiene).
- Depende de: nada externo —cambio contenido en este repo—; `libraauth` ya trae `get_extras`.

## ADR-049 — Roles de usuario: admin, encargado, vendedor, cajero y depósito (más el `staff` heredado), con la matriz en un solo lugar

- Estado: aceptada (decisión del humano, 2026-09-29)
- Fecha: 2026-09-29
- Contexto: hasta hoy el producto sólo tenía `admin` y `staff` (el vocabulario por defecto de la factory de usuarios de
  `libraauth`), los routers se montaban con `admin_only`/`staff_or_admin` en `app/main.py` y la SPA decidía con
  `user.role !== 'admin'` y `adminOnly`. Un comercio real tiene gente que vende, gente que cobra, gente que maneja la mercadería y
  un encargado que hace todo menos administrar el sistema: «admin o no» no alcanza y el dueño terminaba dándole `admin` a todos.
- Decisión: cinco roles, y `staff` sigue.
  - **`admin`**: todo.
  - **`encargado`**: todo menos usuarios, configuración, logs, la estructura del local (sucursales, depósitos y cajas) y reabrir un día
    cerrado.
  - **`vendedor`**: mostrador con clientes: POS, ventas, clientes, cuenta corriente y recibos, consulta de stock y de precios. No ve
    reportes ni márgenes ni el cierre diario.
  - **`cajero`**: POS, su turno y su caja, consulta de stock y de precios, clientes en lectura y alta. No tiene cuenta corriente, cierre
    diario ni reportes.
  - **`deposito`** (sin tilde: es un valor de base y de URL; en pantalla, «Depósito»): stock, ajustes, transferencias y recepción de
    compras; lee productos y proveedores. Sin POS y sin plata: nada de caja, ventas, tesorería, reportes ni márgenes.
  - **`staff`: heredado, migrar a un rol concreto.** Los usuarios que ya existían **no se migran ni se borran**: siguen siendo un rol
    válido con **exactamente** lo que tenían. La pantalla de Usuarios lo ofrece marcado como heredado. El visitante de la demo entra
    como `staff` y conserva su lectura abierta de todas las pantallas.
- **La matriz vive en UN solo archivo: `app/permisos.py`.** Un rol tiene **capacidades** nombradas (`reportes`, `stock.ajustar`,
  `caja.propia`...) y cada router de `app/main.py` se monta con la capacidad que le corresponde (`Depends(requiere("reportes"))`). De esa
  única tabla salen las guardas del backend, el vocabulario de roles de `UserRepository` y del router de usuarios (`roles=ROLES`) y la
  lista `capacidades` que `/auth/login` y `/auth/me` le mandan a la SPA (`get_extras` de `libraauth`, como `modulos` en ADR-048).
  `admin` tiene todas por construcción: una capacidad nueva la trae puesta y la fila dice a quién más se le abre (para un permiso nuevo,
  el error seguro es que lo tenga sólo el admin).
- **Cómo se implementan las guardas** (`app/permisos.py`):
  - `requiere(cap)` es `json_api_require_role(*roles_con(cap))` de `libraauth`, **no una reescritura**: hereda la lectura abierta a la demo
    y el gate de Términos. `requiere_o_servicio(cap)` suma el token de servicio del backoffice y sólo lo usa el router de usuarios
    (`usuarios.admin`): el backoffice sigue sin tocar nada más.
  - Los routers del motor se montan enteros y no admiten una guarda por endpoint: cuando mezclan gente distinta se usa
    `requiere_segun_metodo(lectura=..., escritura=...)` o `requiere_segun_ruta((método, patrón, cap), ..., por_defecto=...)`. Es lo mismo
    que ya hacían `require_staff_lectura_admin_escritura` y `require_staff_precio_admin_resto`, que se retiran de `app/auth.py`.
  - Los ganchos `autorizar_escritura` de cajas, sucursales y depósitos, `solo_admin` de cuenta corriente y recibos, `sesion=` de los
    exports de reportes y `autorizar_reabrir` del cierre diario pasan a las mismas capacidades.
  - Una capacidad mal escrita es un `KeyError` al armar la app, no una ruta abierta.
  - Los routers de correo (`/admin/smtp`) y de códigos de la demo (`/admin/demo-codigos`) los arma `libraauth` y exigen `admin` por
    dentro: no pasan por `permisos.py`, pero coinciden con `config` (sólo admin) y la tabla los cubre.
- **El costo, un filtro de respuesta** (`app/costos.py`, capacidad `costos.ver`). «El vendedor y el cajero no ven costos ni márgenes; el
  depósito, sin plata»: los márgenes, reportes y dashboard ya estaban cerrados por su capacidad, pero el costo unitario viajaba en rutas
  que esos roles sí leen. Los routers del motor lo escriben ellos y no hay guarda por campo, así que un middleware ASGI mira el
  **prefijo** de la ruta (`/api/productos`, `/api/stock`, `/api/depositos`, `/api/proveedores`, `/api/listas-precio`,
  `/api/actualizacion-masiva`, `/api/purchase-orders`, `/api/purchase-receipts`: cubre variantes, escaneo, `?incluir_variantes`, la barra
  final y lo codificado, y todos los métodos) y, si la respuesta es JSON y quien la pidió no tiene `costos.ver`, saca las claves de costo
  en cualquier profundidad. Lee el rol de la base en cada pedido, como la guarda, y **cierra por defecto** (sin sesión, usuario inactivo o
  JSON ilegible: el costo no sale). **No toca los cuerpos de los pedidos**: las escrituras siguen con sus guardas.
  - **Claves de costo medidas** en las respuestas reales: `precio_costo` (lista de productos, detalle de producto en
    `GET /api/stock/{id}`, escaneo `GET /api/productos/escanear`, ítems de `GET /api/listas-precio/{id}/items`), `unit_cost` (líneas de
    órdenes y recepciones de compra, también en la respuesta de `POST .../items` y `.../confirm`) y `subtotal` (líneas de órdenes de
    compra: es cantidad × costo, y se saca sólo bajo `/api/purchase-*`; en una venta es un importe de venta). El patrón general
    (`costo` o `cost` como palabra de la clave) cubre además las que hoy sólo aparecen en rutas de `costos.ver`, `margen` o `logs`:
    `default_cost`, `unit_cost_snapshot`, `costo_actual`, `costo_nuevo`, `costo_estimado`, `sin_costo`. `/auth/captcha` trae un `cost` que es
    la dificultad de la prueba de trabajo: no es un costo y no está bajo ningún prefijo.
  - **Lo que el rol restringido sí recibe**: todo lo demás, idéntico. El depósito ve producto, cantidad pedida, recibida y pendiente de
    cada línea de una orden, y la cantidad de cada línea de una recepción, sin importes. El POS y las promociones no necesitan el costo
    (el de la venta lo toma el servidor) y siguen igual.
  - **Una ruta nueva fuera de esos prefijos no queda cubierta sola.** Por eso el test recorre TODOS los GET de `openapi.json`
    (ver «Cómo se prueba»).
- **Lo que hubo que decidir con criterio** (cada uno se cambia en una línea de `_ROLES_DE`):
  - *Categorías y unidades* (`/catalog/*`) son **configuración**: sólo admin (y el staff heredado, que ya podía: `catalogo.configurar`).
  - *El POS exige turno propio abierto* (`exigir_turno=True`), así que quien vende necesita `caja.propia`: el vendedor la tiene aunque el
    pedido no la nombraba.
  - *El ticket del cierre del propio turno* (`/api/cierre-diario/turno/{id}/ticket`) lo imprime el POS al cerrar el turno: es de
    `caja.propia`, no de `cierre_diario` (el cajero nuevo no tiene cierre diario pero sí necesita ese ticket). **Y es del turno propio de verdad**: el handler del motor imprime el arqueo de cualquier turno por id, así que
    `solo_su_turno_o_todos` (`app/cajas_ganchos.py`) compara `turnos_caja.usuario_id` con la sesión antes de llegar a él (403 con
    «No autorizado», también si el turno ajeno sigue abierto: el 409 del motor contaría que existe). Ver los turnos ajenos es de
    `turnos.todos` (admin y encargado) y de `cierre_diario`: el staff heredado no tiene la primera, pero su vista previa del cierre diario
    ya trae el arqueo de cada turno del día, así que negárselo no protegía nada. Un turno que no existe sigue siendo el 404 del motor.
  - *Anular y devolver ventas* sigue abierto a todo el mostrador (decisión del humano del 2026-09-15: «dejá anular y devolver para el
    cajero también»).
  - *Asignar la lista de precio de un cliente* es una decisión de precio: admin, encargado y staff heredado; no el vendedor.
  - *Baja de un pago de cuenta corriente y anulación de un recibo* (`cobranzas.anular`): admin y encargado (eran de admin).
  - *Libros IVA, dashboard, tesorería, reportes y margen*: admin y encargado.
  - *Logs* y *la estructura del local* (alta, edición y baja de sucursales, depósitos y cajas): sólo admin (mínimo privilegio).
- **La matriz** (`✓` = tiene la capacidad; `admin` las tiene todas):

| Capacidad | Qué abre | admin | encargado | vendedor | cajero | depósito | staff (heredado) |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `usuarios.admin` | Alta, edición, baja y contraseña de usuarios (`/users`); además el token de servicio del backoffice | ✓ |  |  |  |  |  |
| `config` | Datos de empresa y logo, correo (SMTP), ARCA, MercadoPago, backup y resguardo, balanza, ticket | ✓ |  |  |  |  |  |
| `logs` | Log de auditoría (`/logs`) | ✓ |  |  |  |  |  |
| `sucursales.admin` | Alta, edición y baja de sucursales y depósitos | ✓ |  |  |  |  |  |
| `caja.admin` | ABM de cajas | ✓ |  |  |  |  |  |
| `cierre_diario.reabrir` | Reabrir un día cerrado | ✓ |  |  |  |  |  |
| `catalogo.ver` | Leer productos (códigos, variantes), sucursales, depósitos, categorías y unidades | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `catalogo.configurar` | Crear y editar unidades y categorías (`/catalog/*`); el staff la conserva por herencia | ✓ |  |  |  |  | ✓ |
| `productos.escribir` | Alta, edición y baja de productos, códigos y variantes | ✓ | ✓ |  |  |  | ✓ |
| `stock.ver` | Consultar stock, stock por depósito e historial de movimientos | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `stock.ajustar` | Ajustar el stock de un producto | ✓ | ✓ |  |  | ✓ | ✓ |
| `stock.transferir` | Transferir mercadería entre depósitos | ✓ | ✓ |  |  | ✓ | ✓ |
| `precios.consultar` | Leer listas de precio y el precio de una línea (POS) | ✓ | ✓ | ✓ | ✓ |  | ✓ |
| `precios.escribir` | Escribir listas, quiebres, vigencias, promociones y actualización masiva | ✓ | ✓ |  |  |  |  |
| `etiquetas` | Pantalla de etiquetas de góndola (sólo SPA, sin endpoint propio) | ✓ | ✓ |  |  |  |  |
| `ventas.pos` | POS: registrar y cobrar, facturar, QR, tickets, ver, anular y devolver ventas; calcular promociones | ✓ | ✓ | ✓ | ✓ |  | ✓ |
| `caja.propia` | Turno propio (abrir, ver, cerrar), elegir caja y ticket del propio cierre | ✓ | ✓ | ✓ | ✓ |  | ✓ |
| `turnos.todos` | Ver y cerrar los turnos de otros | ✓ | ✓ |  |  |  |  |
| `cierre_diario` | Cierre diario: vista previa, cerrar, historial y tickets | ✓ | ✓ |  |  |  | ✓ |
| `clientes.ver` | Leer clientes y la lista asignada | ✓ | ✓ | ✓ | ✓ |  | ✓ |
| `clientes.alta` | Alta de cliente y consulta de CUIT | ✓ | ✓ | ✓ | ✓ |  | ✓ |
| `clientes.escribir` | Editar, activar y desactivar, alias de facturación, auto-facturar | ✓ | ✓ | ✓ |  |  | ✓ |
| `clientes.lista_precio` | Asignarle a un cliente su lista de precio | ✓ | ✓ |  |  |  | ✓ |
| `cuenta_corriente` | Cuenta corriente y recibos: ver, cobrar y emitir | ✓ | ✓ | ✓ |  |  | ✓ |
| `cobranzas.anular` | Baja de un pago de cuenta corriente y anulación de un recibo | ✓ | ✓ |  |  |  |  |
| `compras.ver` | Leer proveedores, órdenes y recepciones de compra | ✓ | ✓ |  |  | ✓ | ✓ |
| `compras.escribir` | Órdenes de compra; alta, edición y baja de proveedores | ✓ | ✓ |  |  |  | ✓ |
| `compras.recibir` | Recepción de mercadería (crear, cargar líneas, confirmar) | ✓ | ✓ |  |  | ✓ | ✓ |
| `costos.ver` | Ver el costo: `precio_costo` de productos, stock y listas de precio; `unit_cost` y subtotal de las compras. No abre rutas: decide qué campos viajan | ✓ | ✓ |  |  |  | ✓ |
| `egresos` | Egresos | ✓ | ✓ |  |  |  | ✓ |
| `tesoreria` | Tesorería: cuentas y movimientos | ✓ | ✓ |  |  |  |  |
| `libros_iva` | Libros IVA y sus exportaciones | ✓ | ✓ |  |  |  |  |
| `dashboard` | Dashboard | ✓ | ✓ |  |  |  |  |
| `reportes` | Reportes, caja por medio y exportaciones CSV | ✓ | ✓ |  |  |  |  |
| `margen` | Margen y rotación | ✓ | ✓ |  |  |  |  |

- **Turnos ajenos.** El router de turnos de `libracore` decide quién ve y cierra los turnos de otros con `role == "admin"` escrito a mano
  (`caja_router._puede_ver`), sin ganchos. Para que el encargado los vea (`turnos.todos`), `usuario_de_turnos` (`app/cajas_ganchos.py`)
  le presenta `role="admin"` **sólo a ese router**; la sesión real y las guardas (que corren antes, sobre la sesión verdadera) no
  cambian. Cuando el motor reciba esa decisión por parámetro, se muda a él.
- **Usuarios.** `build_users_router(roles=ROLES)` y `UserRepository(roles=ROLES)`: un rol fuera del vocabulario es 422 en el alta y en la
  edición. **No se reimplementó nada de lo que ya trae la factory** de `libraauth`: no dejar la instancia sin admin activo, no sacarse el
  rol de admin ni desactivarse a uno mismo y no borrarse. Sólo el admin (o el token de servicio) administra usuarios. No hay migración de
  datos: `usuarios.role` es `VARCHAR(20)` sin restricción y el más largo, `encargado`, tiene 9.
- **La SPA** (`frontend/src/lib/permisos.ts`): las rutas (`ProtectedRoute cap=...`), el menú (`hideFor: sinCapacidad(...)` en lugar de
  `adminOnly`) y las pantallas con `soloLectura`/`esAdmin` (`Turnos`, `Sucursales`, `SucursalDetalle`, `DepositoDetalle`,
  `CuentaCorrienteDetalle`, `CierreDiario`) miran `puede(user, capacidad)`. La SPA **no tiene una tabla de roles**: sólo los nombres de
  las capacidades (un test del backend falla si se separan de `permisos.py`) y lo que llega en `/auth/me`. Una ruta que no es del rol
  lleva a su pantalla inicial (POS para quien vende, stock para el depósito); un rol sin ninguna de las dos ve un aviso, no un bucle.
  El visitante de la demo (`demo_readonly`) ve todos los menús, como hasta ahora. La pantalla de Usuarios ofrece los roles con la prop
  `roles` que `libra-ui/Usuarios` **ya tenía**: no hizo falta tocar el kit.
- **Cómo se prueba** (una tabla escrita a mano, independiente de `permisos.py`, para que aflojar una capacidad la contradiga):
  - `tests/test_roles_matriz.py`: cada operación que publica `openapi.json` × cada rol (admin, encargado, vendedor, cajero, depósito,
    staff), el visitante de la demo y un anónimo. Una operación nueva sin fila hace fallar el test (un router montado sin decidir quién
    entra se nota), y una fila sin ruta también. Tres rutas que el motor no publica en el esquema (`include_in_schema=False`) van aparte
    en `OCULTAS`. Además: coherencia de la matriz, que toda capacidad tenga una guarda montada, `/auth/me`, que la SPA y el backend
    conozcan las mismas capacidades y roles, y el heredado por nombre.
  - `tests/test_roles_flujos.py`: lo que cada rol hace de punta a punta (vender con turno propio, ver y cerrar turnos ajenos, mover y
    recibir mercadería, el ticket del propio cierre y que el de un turno ajeno sea 403 con dos usuarios reales...). `tests/test_usuarios_roles.py`: el router de usuarios con el vocabulario nuevo.
  - `tests/test_roles_costos.py`: con datos reales (producto con costo, orden y recepción de compra con costo, listas, ventas), cada GET del
    `openapi.json` con el vendedor, el cajero y el depósito: falla si en el JSON aparece una clave de costo **o un valor que sólo el costo tiene**
    (así también atrapa un costo bajo otro nombre); lo que reciben es exactamente la respuesta del admin sin esas claves; admin, encargado y
    staff lo siguen viendo; y no se saltea por barra final, `%70`, HEAD ni rutas hermanas. Sin el middleware, 14 de sus 22 tests se ponen
    rojos.
  - Frontend: `roles-menu-y-rutas.test.tsx` (el menú y el ruteo de cada rol, con las capacidades de `capacidades-por-rol.json`, generado
    desde `permisos.py`: `python -m app.permisos > frontend/src/test/capacidades-por-rol.json`) y `usuarios.test.tsx`.
  - **Verificación diferencial, de una sola vez**: las 209 operaciones privadas que se pueden llamar sin efecto, contra el árbol anterior
    a los roles (sólo `admin` y `staff`) y contra el nuevo, para `admin`, `staff` y el visitante de la demo: **0 diferencias**. Es la
    evidencia de que el heredado conserva lo de hoy.
  - **Mutación**: dejarle `reportes` al cajero pone en rojo su columna de la tabla (6 operaciones), `/auth/me`, el archivo de capacidades
    del frontend y, en vitest, el menú y el ruteo del cajero.
- Consecuencias y **lo que NO resuelve** (a decidir):
  - **El costo ya no viaja a quien no tiene `costos.ver`, pero el kit (`libra-ui`) no sabe que puede faltar** (el filtro está hecho; quedan
    dos consecuencias en las pantallas del kit, medidas):
    - En **Productos** la columna «Precio costo» de un vendedor, un cajero o un depósito muestra `$ NaN` (el kit formatea el campo
      ausente): no se rompe, pero es feo. Se arregla con una prop del kit para no dibujar la columna (`conCosto={false}`); en el detalle de
      una orden de compra, costo unitario y subtotal muestran `NaN` igual.
    - 🔴 **El depósito no puede recibir mercadería desde la pantalla «Recibir mercadería» del kit**: precarga el costo de cada línea desde
      la orden y lo manda como `unit_cost`; sin el campo en la respuesta manda la línea sin él y el motor la rechaza con 422 (`unit_cost`
      es obligatorio en `RecepcionItemPayload`; medido). Por la API sí recibe (con un `unit_cost` en el cuerpo). Cerrarlo pide que el motor
      acepte la línea sin costo cuando quien recibe no lo ve (usar el de la línea de la orden, o el del producto) **sin pisar** el costo del
      producto: `confirm` deja el `unit_cost` recibido como nuevo costo (último costo), así que un depósito que mande un importe cualquiera
      lo cambia. Es un pedido a `libracommerce` y al kit; hasta entonces la recepción desde la pantalla la hace un encargado.
  - **El kit (`libra-ui`) no tiene modo de sólo lectura** en Productos, Stock, Clientes, Proveedores ni Compras: un rol que lee pero no
    escribe ve los botones de alta y edición y recibe el 403 del backend al usarlos. Queda como pedido al kit (una prop `soloLectura` por
    pantalla, como ya tienen Sucursales y Depósitos). Y la ficha de un cliente le muestra al cajero la tarjeta de cuenta corriente con un
    error (no tiene `cuenta_corriente`).
  - **El cajero no tiene cuenta corriente ni recibos**: la matriz aprobada no se los da (sí al vendedor). Hasta hoy el cajero (`staff`)
    cobraba fiado en el mostrador (ADR-031); con el rol nuevo lo hace el vendedor. Es una línea (`cuenta_corriente`) si no era la intención.
  - **El cajero pierde el cierre diario** (ADR de 2026-09-13: «admin o cajero»): ahora es del encargado y del admin. El `staff` heredado
    lo conserva.
  - Una ruta nueva que el motor publique con `include_in_schema=False` no la ve el test de cobertura: hoy son tres y están en `OCULTAS`.
- Depende de: nada externo —cambio contenido en este repo—; `libraauth` (`get_extras`, `build_users_router(roles=...)`) y `libra-ui`
  v0.88.0 (`Usuarios` con la prop `roles`).
