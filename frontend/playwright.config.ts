import { definirConfig } from 'libra-ui/e2e'

// Tests de navegador (F6.3 y de dominio). Corren contra la app REAL levantada por el workflow: uvicorn sirviendo `dist/`
// en localhost (`.github/workflows/smoke-navegador.yml` y `e2e.yml`, ambos con la Action `libra-web-kit/e2e-ci`).
// La base (Chromium, un worker, retries 0 en el PR y 1 de noche, trace y screenshot al fallar) es de `libra-ui/e2e`;
// acá sólo hay que decir qué proyecto corre cada archivo:
//   - `smoke`: `e2e/*.smoke.ts`, el login y la primera pantalla (en cada PR).
//   - `setup`: `e2e/*.setup.ts`, deja la sesión de cada rol en `.auth/`.
//   - `e2e`:   `e2e/*.e2e.ts`, los flujos de dominio. Depende de `setup`.
// Los archivos no terminan en `.test.ts` para que vitest, que colecta `src/**/*.test.*`, no los levante.
export default definirConfig()
