# Decisiones arquitectónicas — TiendaLibra

Registro ADR. No borrar decisiones: si dejan de aplicar, marcarlas como
reemplazadas.

## ADR-001 — Componer LibraCommerce en vez de reimplementar catálogo/inventario/ventas

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: el roadmap de la familia Libra (`wiki/analyses/arquitectura-familia-libra-alcance.md`)
  ya define LibraCommerce como el motor reutilizable de catálogo, compras,
  inventario y ventas, con esquema SQLite y `SqliteCommerceRepository`
  estables (55 tests pasando al momento de esta decisión).
- Decisión: TiendaLibra depende de `libracommerce` como paquete versionado
  (git tag), no copia ni reimplementa su dominio.
- Consecuencias: TiendaLibra queda acoplado al ritmo de release de
  LibraCommerce; cualquier extensión de catálogo que otro vertical también
  necesite (código de barras, variantes, listas de precio) debe evaluarse
  primero como cambio en LibraCommerce, no como parche local.
- Alternativas descartadas: reimplementar un catálogo/inventario propio
  dentro de TiendaLibra — descartado porque duplicaría exactamente lo que
  LibraCommerce ya resuelve y probó contra datos reales de Contalibra.

## ADR-002 — Tabla `users` propia en vez de `libracore.db.usuarios`

- Estado: aceptada
- Fecha: 2026-07-25
- Contexto: `libracore.db.usuarios` ya resuelve alta/baja/auth de usuarios
  contra SQLite, y TiendaLibra (a diferencia de GestioLibra/MedLibra, que
  usan SQLAlchemy/Postgres para su dominio propio) es 100% SQLite nativo, así
  que técnicamente podría reusarlo sin el problema de acoplamiento que tienen
  esos dos productos.
- Decisión: TiendaLibra mantiene su propia tabla `users` y su propio
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
  TiendaLibra en Fase 1 no usa ningún módulo de `libracore.db` todavía (solo
  `libracore.auth`, que no toca SQLite).
- Decisión: Fase 1 usa una única base SQLite (`data/tiendalibra.db`) para
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
- Consecuencias: TiendaLibra ya no mantiene dos copias de la misma lógica
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
- Consecuencias: TiendaLibra deja de depender de una tabla de implementación
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
  3 fallos, en módulos sin ninguna relación con TiendaLibra).
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
  TiendaLibra, ni de ningún producto de la familia — revertidos todos los
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
  portado a TiendaLibra casi verbatim en la mecánica (`configure()`,
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
- Consecuencias: TiendaLibra diverge del patrón exacto de MedLibra/Gestiolibra
  en el punto de "cuándo toca caja" — es una decisión de dominio real
  (retail vs. turnos), no una inconsistencia accidental; documentado acá
  para que quede claro que es intencional si alguien compara los tres
  `billing.py` lado a lado.
- Alternativas descartadas: automatizar la factura cuando el cliente tiene
  CUIT cargado (sin flag explícito) — descartado, el usuario prefirió
  control explícito por venta; caja solo si hay factura (mismo patrón
  exacto que MedLibra/Gestiolibra) — descartado, no refleja cómo funciona
  el control de caja en un comercio real.
