import type { Rol } from './roles'

// Lo que cada rol tiene que ver, escrito a mano e independiente del código de la SPA (`components/Layout.tsx`, `lib/permisos.ts`): es
// la misma idea que la tabla de `tests/test_roles_matriz.py` del backend. Si alguien afloja un permiso o suma una pantalla al menú,
// esto se pone rojo a propósito y hay que decidir, mirando la matriz de `app/permisos.py` (ADR-049), si está bien.

const ADMIN = [
  '/dashboard', '/pos', '/ventas', '/comprobantes-pendientes', '/clientes', '/cuentas-corrientes', '/turnos', '/cierre-diario', '/cajas', '/tesoreria',
  '/egresos', '/productos', '/etiquetas', '/listas-precio', '/actualizacion-masiva-precios', '/promociones', '/stock',
  '/vencimientos', '/transferencias', '/reposicion', '/sucursales', '/compras', '/proveedores', '/reportes', '/margen', '/mermas',
  '/caja-medios', '/libros-iva', '/usuarios', '/logs', '/configuracion',
]

// El encargado: todo menos usuarios, configuración, logs y la estructura (cajas, sucursales y depósitos se le ofrecen sólo por
// `stock.transferir`: ve «Sucursales y depósitos» pero no «Cajas»).
const ENCARGADO = ADMIN.filter((r) => !['/cajas', '/usuarios', '/logs', '/configuracion'].includes(r))

/** Los links del sidebar de cada rol (sin orden). */
export const MENU_POR_ROL: Record<Rol, string[]> = {
  admin: ADMIN,
  encargado: ENCARGADO,
  vendedor: ['/pos', '/ventas', '/clientes', '/cuentas-corrientes', '/turnos', '/productos', '/stock'],
  cajero: ['/pos', '/ventas', '/turnos'],
  deposito: ['/productos', '/stock', '/vencimientos', '/transferencias', '/reposicion', '/sucursales', '/compras'],
}

/** A dónde cae cada rol al entrar (`inicioDe`): el dashboard si lo ve, si no el POS si vende, si no el stock. */
export const INICIO_POR_ROL: Record<Rol, string> = {
  admin: '/dashboard',
  encargado: '/dashboard',
  vendedor: '/pos',
  cajero: '/pos',
  deposito: '/stock',
}

/** Una ruta que el rol NO tiene, y a dónde lo manda la SPA, y el endpoint que además se la corta en el servidor. */
export const PROHIBIDA_POR_ROL: Partial<Record<Rol, { ruta: string; cae: string; endpoint: string }>> = {
  encargado: { ruta: '/usuarios', cae: '/dashboard', endpoint: '/users' },
  vendedor: { ruta: '/reportes', cae: '/pos', endpoint: '/api/reportes' },
  cajero: { ruta: '/usuarios', cae: '/pos', endpoint: '/users' },
  deposito: { ruta: '/pos', cae: '/stock', endpoint: '/api/ventas' },
}
