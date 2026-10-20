// El menú de VentaLibra usa los íconos del catálogo de la familia (libra-ui ADR-035, `libra-ui/iconos-identidad`).
//
// 🔴 **Lee el FUENTE del `Layout.tsx`**, no el DOM: el menú no se exporta y lo que hay que impedir es que vuelva a divergir. Es el mismo criterio
// que `titulos-con-icono.test.ts`, que cubre la otra mitad (el título de cada pantalla = el ícono de su entrada).
//
// `RUTA_A_CONCEPTO` es la tabla de ESTE producto: qué concepto del catálogo es cada entrada del menú. Una entrada que no está acá es un concepto
// propio del producto (Margen, Vencimientos, Transferencias, Reposición, Etiquetas, Promociones, Actualización de precios): su ícono no es del
// catálogo, pero tampoco puede ser uno que el catálogo le da a otro concepto, ni repetirse con otra entrada del menú.
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import * as lucide from 'lucide-react'
import { ICONOS, type Concepto } from 'libra-ui/iconos-identidad'
import { auditarMenuContraCatalogo, iconosDelNav, resolverAlias } from 'libra-ui/auditoria-de-titulos'

const SRC = join(process.cwd(), 'src')
const LAYOUT = readFileSync(join(SRC, 'components', 'Layout.tsx'), 'utf8')

const RUTA_A_CONCEPTO: Record<string, Concepto> = {
  '/dashboard': 'dashboard',
  // El POS y la lista de ventas son el mismo concepto del catálogo («Ventas / POS»): comparten ícono.
  '/pos': 'ventas',
  '/ventas': 'ventas',
  '/clientes': 'clientes',
  '/cuentas-corrientes': 'cuentaCorriente',
  '/turnos': 'turnosDeCaja',
  '/cierre-diario': 'cierreDiario',
  '/cajas': 'cajas',
  '/tesoreria': 'tesoreria',
  '/egresos': 'egresos',
  '/productos': 'productos',
  '/listas-precio': 'listasDePrecio',
  '/stock': 'stock',
  '/sucursales': 'sucursales',
  '/compras': 'ordenesDeCompra',
  '/proveedores': 'proveedores',
  '/reportes': 'reportes',
  '/caja-medios': 'cajaPorMedio',
  '/libros-iva': 'librosDeIva',
  '/usuarios': 'usuarios',
  '/logs': 'logDeActividad',
  '/configuracion': 'configuracion',
}

/** El nombre de lucide al que apunta el `icon:` de una entrada del menú (resuelve el `as` del import y el `ICONOS.x` del catálogo). */
function iconoDe(expresion: string): string {
  const miembro = /^ICONOS\.([a-z][A-Za-z0-9]*)$/.exec(expresion)
  const nombre = miembro ? '' : resolverAlias(LAYOUT, expresion)
  const componente = miembro ? ICONOS[miembro[1] as Concepto] : (lucide as unknown as Record<string, unknown>)[nombre]
  return (componente as { displayName?: string } | undefined)?.displayName ?? expresion
}

describe('el menú usa los íconos del catálogo de la familia', () => {
  it('🔴 cada entrada de un concepto del catálogo lleva el ícono de ese concepto', () => {
    const { mal, faltan, medidas } = auditarMenuContraCatalogo(LAYOUT, RUTA_A_CONCEPTO, 'ventalibra')
    expect(mal).toEqual([])
    expect(faltan).toEqual([])
    // El control: sin esto, dos listas vacías contra dos listas vacías serían un verde si el parser dejara de leer el menú.
    expect(medidas).toBe(Object.keys(RUTA_A_CONCEPTO).length)
  })

  it('🔴 una entrada propia del producto no usa un ícono del catálogo ni uno que ya tiene otra entrada', () => {
    const delCatalogo = new Map(Object.entries(ICONOS).map(([concepto, icono]) => [(icono as { displayName?: string }).displayName, concepto]))
    const porIcono = new Map<string, string[]>()
    const choques: string[] = []
    let propias = 0
    for (const [ruta, expresion] of iconosDelNav(LAYOUT)) {
      const icono = iconoDe(expresion)
      porIcono.set(icono, [...(porIcono.get(icono) ?? []), ruta])
      if (ruta in RUTA_A_CONCEPTO) continue
      propias++
      const concepto = delCatalogo.get(icono)
      if (concepto) choques.push(`${ruta}: ${icono} es el ícono de «${concepto}»`)
    }
    for (const [icono, rutas] of porIcono) {
      // Dos entradas pueden compartir ícono sólo si son el mismo concepto del catálogo (acá: el POS y la lista de ventas).
      const conceptos = new Set(rutas.map((r) => RUTA_A_CONCEPTO[r] ?? r))
      if (conceptos.size > 1) choques.push(`${icono} se repite en ${rutas.join(', ')}`)
    }
    expect(choques).toEqual([])
    expect(propias).toBeGreaterThan(0)
  })
})
