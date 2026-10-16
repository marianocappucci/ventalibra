// Guard: todo campo donde se elige un cliente ofrece darlo de alta ahí mismo (ADR-071 del kit, libra-ui v0.158.0; ADR-087 de este repo).
//
// 🔴 **Lee los FUENTES, no el DOM**, igual que `selects-buscables.test.ts`: lo que hay que impedir es que vuelva a nacer un desplegable de cliente que
// no sea `SelectCliente`. Un filtro de listado que no crea nada se marca con `cliente-sin-alta: <motivo>` en el renglón o en los tres de arriba.
//
// ⚠️ **En VentaLibra el guard mide cero campos, y está bien.** El cliente se elige en dos lugares: las pantallas del kit (Ventas, Presupuestos,
// Clientes…), que ya traen su `SelectCliente` y se guardan allá, y el diálogo «Cliente de la venta» del POS, que no es un desplegable sino una
// lista con teclado —el guard sólo mira `<Select>`/`<SelectBuscable>`— y por eso NO lo detecta. El POS se cubre con su propio test de comportamiento
// (`pos-elegir-cliente.test.tsx`: «Nuevo cliente» → `POST /api/clientes` → queda elegido). Por eso el control positivo no puede ser `campos > 0`:
// sólo se exige que haya leído archivos.
import { describe, expect, it } from 'vitest'
import { join } from 'node:path'
import { auditarCamposDeCliente, describirCamposSinAlta } from 'libra-ui/auditoria-de-clientes'

const SRC = join(process.cwd(), 'src')

describe('todo campo de cliente ofrece el alta ahí mismo', () => {
  const r = auditarCamposDeCliente(SRC)

  it('🔴 el control — el guard leyó los fuentes (un parser que no lee nada sería un falso verde)', () => {
    expect(r.archivos).toBeGreaterThan(0)
    // El POS no es un desplegable: se cubre con su test de comportamiento (ver arriba). Si algún día aparece un campo de cliente propio, tiene que ser SelectCliente.
    expect(r.campos).toBeGreaterThanOrEqual(0)
  })

  it('🔴 ningún campo de cliente es un desplegable sin alta', () => {
    expect(describirCamposSinAlta(r.infracciones)).toEqual([])
  })
})
