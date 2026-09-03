# Arquitectura — VentaLibra

Descripción del estado técnico actual. Las decisiones y sus motivos viven en
`DECISIONS.md`.

## Propósito y límites

VentaLibra es la API y producto vertical para despensas, autoservicios,
comercios de alimentos y tiendas de ropa. Cubre la experiencia de POS,
catálogo, inventario, compras y (en fases posteriores) caja/facturación
propias del rubro minorista. No reimplementa dominio de catálogo, inventario,
compras o ventas — todo eso vive en LibraCommerce; VentaLibra aporta el flujo
HTTP, auth propia y la orquestación de casos de uso entre motores.

## Componentes

- **Aplicación**: FastAPI, factory en `app/main.py` (patrón idéntico a
  GestioLibra/MedLibra: `create_app(...)` configura las conexiones y monta
  routers con gating por rol a nivel de `include_router`).
- **Persistencia**: una única base SQLite en Fase 1
  (`data/ventalibra.db`), abierta directamente (no hay pool ni ORM — mismo
  estilo que LibraCommerce). Contiene el esquema de LibraCommerce
  (`libracommerce.db.schema.init_schema`) más una tabla `users` propia
  (`app/db.py::init_users_schema`). Ver `DECISIONS.md` ADR-002 sobre por qué
  no se reusa `libracore.db.usuarios` en esta fase.
- **Motor de catálogo/inventario/ventas**: `libracommerce.db.repository.SqliteCommerceRepository`,
  compartiendo la misma conexión sqlite3 que el resto de la app.
- **Auth**: `libracore.auth.SessionAuth` (cookie firmada `tl_session`),
  igual mecánica que GestioLibra/MedLibra — dependencias propias
  (`get_current_user`/`require_role`) devuelven 401/403 JSON en vez de
  redirect, porque es una API sin páginas HTML.
- **Integraciones futuras**: LibraCore (`caja`, `arca_facturacion`) en Fase 3,
  sobre una segunda base SQLite dedicada — ver `ROADMAP.md`.

## Flujo principal (Fase 1)

1. Un admin hace login (`POST /auth/login`) y da de alta categorías,
   unidades, items de catálogo y ubicaciones (depósito/sucursal).
2. Un staff (o admin) crea una venta en borrador
   (`POST /sales`), le agrega líneas (`POST /sales/{id}/items` — cada línea
   toma un snapshot de descripción/precio/costo del `CatalogItem` en ese
   momento) y la confirma (`POST /sales/{id}/confirm`).
3. Confirmar la venta recalcula los totales, fija `status=confirmed` y
   `confirmed_at`, y por cada línea de tipo `product` genera un
   `StockMovement` de tipo `sale` con cantidad negativa en la ubicación
   indicada — la orquestación venta→stock que LibraCommerce deja
   deliberadamente afuera de su repositorio (ver `wiki/entities/libracommerce.md`).
4. `GET /stock/{item_id}?location_id=` expone `current_stock` (proyección de
   la suma de movimientos, nunca editable directamente).

## Entornos y deploy

- Dev/demo/producción: pendientes de provisionar (arquitectura silo,
  mismo patrón que Contalibra/Restolibra/GestioLibra/MedLibra — un
  contenedor y una base SQLite por cliente).
- CI: GitHub Actions corre `pytest` en cada push/PR (`.github/workflows/`).

## Riesgos y límites conocidos

- LibraCommerce todavía no tiene códigos de barra, variantes ni listas de
  precio — el catálogo de Fase 1 es deliberadamente simple (nombre,
  categoría, unidad, precio/costo por defecto).
- Sin caja ni facturación todavía: una venta confirmada no genera ningún
  movimiento financiero ni comprobante. Fase 3.
- Una sola base SQLite compartida entre LibraCommerce y `users` — al llegar
  la Fase 3 se suma una segunda base para LibraCore, replicando el patrón ya
  probado en MedLibra.
