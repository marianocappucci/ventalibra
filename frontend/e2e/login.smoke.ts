import { expect, test, type Page } from '@playwright/test'

// El captcha «No soy un robot» (ALTCHA, libraauth v0.40.0 con `captcha=True`):
// «Ingresar» queda deshabilitado hasta que el widget resuelve el desafío, que
// es una prueba de trabajo de alrededor de un segundo en el navegador. El
// checkbox vive en el shadow DOM abierto del web component; `getByRole` lo
// atraviesa. El tope de 30 s es para un runner de CI lento, no lo esperado.
async function tildarCaptcha(page: Page) {
  await page.getByRole('checkbox', { name: 'No soy un robot' }).click()
  await expect(page.getByRole('button', { name: 'Ingresar' })).toBeEnabled({ timeout: 30_000 })
}

// Lo único que un unitario no puede ver: que la SPA construida, servida por la
// app real, deje entrar y muestre una pantalla de dominio. Si el bundle quedó
// viejo, si el gate de Términos tapa todo, si el login devuelve HTML por el
// catch-all en vez de JSON, esto se pone rojo y los unitarios no.
//
// Los campos se ubican por los `id` que pone `createLogin` de libra-ui
// (`#username`, `#password`): `getByLabel('Contraseña')` matchea también al
// botón «Mostrar contraseña», y el nombre del producto es un wordmark, no un
// heading accesible. La primera pantalla se reconoce por el sidebar de libra-ui
// (`data-sidebar="sidebar"`).
test('entra por /login, acepta los Términos y ve la primera pantalla', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()

  await page.locator('#username').fill(process.env.SMOKE_USER ?? 'admin')
  await page.locator('#password').fill(process.env.SMOKE_PASSWORD ?? '')
  await tildarCaptcha(page)
  await page.getByRole('button', { name: 'Ingresar' }).click()
  await expect(page).toHaveURL(/\/pos/)

  // Una instancia recién nacida pone el gate de Términos y Condiciones delante
  // de todo (libraauth v0.34.0, libra-ui GateTerminos): es lo que ve un cliente
  // nuevo, y lo que en agosto dejó las ocho demos "vacías" sin que ningún
  // unitario lo viera. El smoke lo atraviesa como el humano: tilda, acepta.
  await expect(page.getByRole('heading', { name: /Términos y Condiciones/ })).toBeVisible()
  await page.getByRole('checkbox', { name: /Leí y acepto/ }).check()
  await page.getByRole('button', { name: 'Aceptar y continuar' }).click()

  await expect(page.locator('[data-sidebar="sidebar"]').first()).toBeVisible()
  await expect(page.locator('#username')).toHaveCount(0)
})

test('una credencial mala no entra (control)', async ({ page }) => {
  // Sin esto el test de arriba podría pasar con un login que acepte cualquier
  // cosa; el rechazo tiene que verse en la pantalla, no sólo en la API.
  await page.goto('/login')
  await page.locator('#username').fill('admin')
  await page.locator('#password').fill('esta-no-es')
  // Con el captcha tildado: sin él el botón está deshabilitado y el control
  // no llegaría a probar la contraseña.
  await tildarCaptcha(page)
  await page.getByRole('button', { name: 'Ingresar' }).click()
  await expect(page).toHaveURL(/\/login/)
  await expect(page.locator('p.text-destructive')).toBeVisible()
  await expect(page.locator('#username')).toBeVisible()
})
