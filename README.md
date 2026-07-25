# TiendaLibra

Vertical de la familia Libra para despensas, autoservicios, comercios de
alimentos, tiendas de ropa y comercios minoristas en general. Cubre catálogo,
inventario, compras y ventas/POS componiendo dos motores reutilizables:
[LibraCommerce](https://github.com/marianocappucci/libracommerce) (catálogo,
compras, inventario, ventas) y
[LibraCore](https://github.com/marianocappucci/libracore) (auth, caja,
facturación ARCA — se incorpora en fases posteriores).

Alcance completo, arquitectura de la familia y orden de implementación
documentados en la wiki del ecosistema
(`wiki/analyses/arquitectura-familia-libra-alcance.md` y
`wiki/entities/tiendalibra.md`).

## Estado

- Fase 1 en desarrollo: auth + catálogo + inventario + venta POS básica,
  wireados de punta a punta sobre LibraCommerce/LibraCore.
- Entorno dev: `dev.tiendalibra.com.ar` (pendiente de provisionar).
- Demo: `demo.tiendalibra.com.ar` (pendiente).
- Producción: `cliente.tiendalibra.com.ar` (pendiente, arquitectura silo por cliente).
- Rama de desarrollo: `develop`.
- Rama de producción: `main` (todavía no creada — se abre cuando haya un
  primer corte deployable).

## Documentación relacionada

- [ROADMAP.md](ROADMAP.md)
- [TASKS.md](TASKS.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [CONVENTIONS.md](CONVENTIONS.md)
- [DECISIONS.md](DECISIONS.md)
- [CHANGELOG.md](CHANGELOG.md)
