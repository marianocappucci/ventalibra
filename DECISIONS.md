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
