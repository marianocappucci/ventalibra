// Config de tests aparte del vite.config.ts, y no un bloque `test` dentro
// de el: asi el build de produccion no arrastra tipos ni opciones de
// Vitest. Se reusa la config de Vite (con su alias `@`) via mergeConfig,
// para que los tests resuelvan los imports igual que la app.
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    // `@vitejs/plugin-react` no toca node_modules, asi que los .tsx de
    // libra-ui los transpila esbuild -- y por defecto usa el runtime
    // CLASICO, que emite `React.createElement` sin que React este
    // importado: "React is not defined" al primer render. Con `automatic`
    // usa el mismo runtime que el resto de la app.
    esbuild: { jsx: 'automatic' },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      server: {
        deps: {
          // `libra-ui` se consume como CODIGO FUENTE (.tsx) desde
          // node_modules -- sus `exports` apuntan a src/. Vitest por
          // defecto no transforma node_modules, asi que ese JSX llegaria
          // sin compilar y todo revienta con "React is not defined".
          // Inlinearlo lo hace pasar por el pipeline de Vite, igual que en
          // el build real del producto.
          inline: ['libra-ui'],
        },
      },
    },
  }),
)
