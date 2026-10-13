import { entrarComo, expect, SIDEBAR, test } from 'libra-ui/e2e'
import { INICIO_POR_ROL, MENU_POR_ROL, PROHIBIDA_POR_ROL } from './menus'
import { ROLES, type Rol } from './roles'

// El login de cada rol, por la pantalla y sin sesión previa (el proyecto `setup` también entra por ahí, pero acá es lo que se
// prueba): cada uno cae en su pantalla inicial, ve SU menú y ni más ni menos, y una ruta que no tiene lo devuelve a su
// inicio sin mostrarla. La SPA sólo decide qué se ofrece: el que corta de verdad es el backend, así que la misma
// pregunta se le hace por la API con la sesión que recién abrió el navegador.
test.use({ rol: null })

for (const rol of Object.keys(ROLES) as Rol[]) {
  test(`${rol}: entra, cae en su inicio, ve su menú y no entra a lo que no tiene`, async ({ page }) => {
    await entrarComo(page, ROLES[rol])
    // Tras el login todos caen en `/pos` (y los que no venden, en lo suyo); la raíz es la que resuelve el inicio de cada rol.
    await page.goto('/')
    await expect(page).toHaveURL(new RegExp(`${INICIO_POR_ROL[rol]}$`))
    await expect(page.locator(SIDEBAR).first()).toBeVisible()

    const enlaces = await page.locator(`${SIDEBAR} a`).evaluateAll((as) => as.map((a) => a.getAttribute('href')))
    expect([...enlaces].sort()).toEqual([...MENU_POR_ROL[rol]].sort())

    const prohibida = PROHIBIDA_POR_ROL[rol]
    if (!prohibida) return
    await page.goto(prohibida.ruta)
    await expect(page).toHaveURL(new RegExp(`${prohibida.cae}$`))
    // El servidor, además, la corta: 403 y no los datos.
    const respuesta = await page.request.get(prohibida.endpoint)
    expect(respuesta.status(), `${rol}: GET ${prohibida.endpoint}`).toBe(403)
  })
}
