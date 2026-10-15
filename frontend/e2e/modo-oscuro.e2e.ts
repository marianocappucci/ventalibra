import { expect, ponerModo, sinTextoIlegible, test } from 'libra-ui/e2e'
import { abrirTurno, cerrarTurno, crearProducto } from './datos'
import { MENU_POR_ROL } from './menus'
import { agregarAlTicket } from './pos'

// El modo oscuro, probado en un navegador real: todo texto visible de cada pantalla del menú del admin llega al contraste mínimo (WCAG AA, 4,5:1; 3:1 el texto grande).
// Es la pasada visual que se hizo a mano el 2026-10-02 (el nombre del producto casi invisible, el verde de éxito a 4,28:1), automática: un `text-[#2d2d2d]` fijo o un token
// sin variante oscura pone rojo el PR que lo introduce. `ponerModo` / `sinTextoIlegible` son de `libra-ui/e2e` (v0.152.0); el modo se guarda por navegador en
// `localStorage` y se aplica antes del primer cuadro, igual que cuando alguien lo elige con el botón sol/luna.
//
// Mide texto, no bordes, íconos ni gráficos, y no mide el texto sobre un fondo con degradé o imagen (ver `sinTextoIlegible`). Si una pantalla tiene algo que se ve
// igual en los dos modos a propósito, se exime con `ignorar: '<selector>'` y la razón escrita acá, no aflojando el mínimo.

test.describe('modo oscuro: el texto se lee en cada pantalla del menú', () => {
  test.use({ rol: 'admin' })

  for (const ruta of MENU_POR_ROL.admin) {
    test(`${ruta}`, async ({ page }) => {
      await ponerModo(page, 'oscuro')
      await page.goto(ruta)
      // Con los datos ya cargados, como en el spec de desbordes: el texto de «Cargando…» no es el de la pantalla.
      await expect(page.getByRole('heading', { level: 2 }).or(page.getByText(/Nueva venta|No hay ningún turno/)).first()).toBeVisible()
      await expect(page.getByText(/^Cargando/)).toHaveCount(0)
      await sinTextoIlegible(page)
    })
  }

  test.describe('el POS con una venta armada', () => {
    test.use({ rol: 'cajero' })

    test('/pos con un turno abierto y una línea en el ticket', async ({ page, api, apiDe }) => {
      const admin = await apiDe('admin')
      const producto = await crearProducto(admin, { precio: 1_234 })
      await abrirTurno(api, admin)
      try {
        await ponerModo(page, 'oscuro')
        await page.goto('/pos')
        await agregarAlTicket(page, `3 * ${producto.nombre}`, new RegExp(producto.nombre))
        await sinTextoIlegible(page)
      } finally {
        await cerrarTurno(api)
      }
    })
  })
})
