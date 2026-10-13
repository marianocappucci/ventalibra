import { expect, sinDesborde, test } from 'libra-ui/e2e'
import { abrirTurno, cerrarTurno, crearProducto } from './datos'
import { MENU_POR_ROL } from './menus'
import { agregarAlTicket } from './pos'

// Lo que sólo ve un navegador real, y que ya rompió: las pestañas atadas a la URL donde «atrás» no volvía a la anterior, y las
// pantallas que se desbordan a lo ancho en un celular (390 px) y no en el monitor (1280 px).

test.describe('Configuración: las pestañas viven en la URL y «atrás» vuelve a la anterior', () => {
  test.use({ rol: 'admin' })

  test('cada pestaña es un paso del historial', async ({ page }) => {
    const pestana = (nombre: string) => page.getByRole('tab', { name: nombre, exact: true })

    await page.goto('/configuracion')
    await expect(pestana('Empresa')).toHaveAttribute('aria-selected', 'true')

    await pestana('Balanza').click()
    await expect(page).toHaveURL(/\/configuracion\?seccion=balanza$/)
    await expect(pestana('Balanza')).toHaveAttribute('aria-selected', 'true')

    await pestana('Ticket').click()
    await expect(page).toHaveURL(/\/configuracion\?seccion=ticket$/)
    await expect(pestana('Ticket')).toHaveAttribute('aria-selected', 'true')

    // Atrás: Ticket -> Balanza -> la de entrada, con la pestaña marcada al día en cada paso.
    await page.goBack()
    await expect(page).toHaveURL(/\/configuracion\?seccion=balanza$/)
    await expect(pestana('Balanza')).toHaveAttribute('aria-selected', 'true')
    await expect(pestana('Ticket')).toHaveAttribute('aria-selected', 'false')

    await page.goBack()
    await expect(page).toHaveURL(/\/configuracion$/)
    await expect(pestana('Empresa')).toHaveAttribute('aria-selected', 'true')

    // Y adelante, otra vez a la que se había ido.
    await page.goForward()
    await expect(pestana('Balanza')).toHaveAttribute('aria-selected', 'true')
  })

  test('un link directo a una pestaña la abre, y «atrás» sale de Configuración', async ({ page }) => {
    await page.goto('/dashboard')
    await page.goto('/configuracion?seccion=categorias')
    await expect(page.getByRole('tab', { name: 'Categorías', exact: true })).toHaveAttribute('aria-selected', 'true')
    await page.goBack()
    await expect(page).toHaveURL(/\/dashboard$/)
  })
})

test.describe('sin desborde a 390 y a 1280 px', () => {
  // Las rutas salen de la tabla del menú del admin (`menus.ts`), que el spec de roles verifica contra el sidebar real: una
  // pantalla nueva entra acá en cuanto entra al menú.
  test.use({ rol: 'admin' })

  for (const ruta of MENU_POR_ROL.admin) {
    test(`${ruta}`, async ({ page }) => {
      await page.goto(ruta)
      // Con los datos ya cargados: un desborde que viene de una fila larga no existe mientras dice «Cargando…».
      await expect(page.getByRole('heading', { level: 2 }).or(page.getByText(/Nueva venta|No hay ningún turno/)).first()).toBeVisible()
      await expect(page.getByText(/^Cargando/)).toHaveCount(0)
      await sinDesborde(page, [390, 1280])
    })
  }

  test.describe('el POS con una venta armada', () => {
    test.use({ rol: 'cajero' })

    test('/pos con un turno abierto y una línea en el ticket', async ({ page, api, apiDe }) => {
      // Desborde REAL que encontró este spec (2026-10-12) y se arregló: las columnas del ticket (`Ticket` en `pages/Pos.tsx`) sumaban 352 px
      // de anchos fijos y a 390 px el contenedor mide 343, así que la tabla quedaba recortada y el «Quitar línea» pegado al borde. Ahora
      // las columnas se adaptan al ancho del ticket (container query): este test es el que lo cuida.
      const admin = await apiDe('admin')
      const producto = await crearProducto(admin, { precio: 1_234 })
      await abrirTurno(api, admin)
      try {
        await page.goto('/pos')
        await agregarAlTicket(page, `3 * ${producto.nombre}`, new RegExp(producto.nombre))
        await sinDesborde(page, [390, 1280])
      } finally {
        await cerrarTurno(api)
      }
    })
  })
})
