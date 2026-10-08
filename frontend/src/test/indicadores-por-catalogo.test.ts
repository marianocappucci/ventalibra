// Guard: los reportes y los tableros toman sus íconos del catálogo, no de lucide (ADR-038, libra-ui v0.128.0).
//
// 🔴 **Lee los FUENTES, no el DOM.** Lo que hay que impedir no es que una pantalla se rompa sino que vuelvan a divergir: que el próximo
// reporte importe un ícono de lucide porque quedaba bien y el menú diga otra cosa. Eso se ve en el `import`, no en un render. El motor
// vive en `libra-ui/auditoria-de-indicadores` y tiene sus propios tests allá.
//
// Hoy `Dashboard` y `Reportes` son wrappers del kit (`libra-ui/comercio`), que ya toma los íconos del catálogo: el guard queda para la
// primera pantalla de reporte o de tablero propia que se escriba acá.
import { describe, expect, it } from 'vitest'
import { join } from 'node:path'
import { auditarIndicadores, describirInfracciones } from 'libra-ui/auditoria-de-indicadores'

const SRC = join(process.cwd(), 'src')

describe('los reportes y tableros usan el catálogo de íconos', () => {
  const r = auditarIndicadores(SRC)

  it('🔴 el control — el guard midió algo (un parser que devuelve cero sería un falso verde)', () => {
    expect(r.archivos).toBeGreaterThan(0)
    expect(r.pantallas).toBeGreaterThan(0)
  })

  it('🔴 ninguna pantalla de reporte o de tablero importa un ícono de concepto de lucide', () => {
    expect(describirInfracciones(r.infracciones)).toEqual([])
  })
})
