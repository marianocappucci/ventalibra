import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Proxy de API en dev: mismo origen que el front (localhost:5173) hacia
// el backend FastAPI (localhost:8000) para que la cookie de sesion
// (vl_session) funcione sin lidiar con CORS/SameSite cross-origin --
// mismo truco que se usa en produccion, donde el build de este frontend
// se sirve desde el mismo proceso FastAPI (ver app/asgi.py).
const API_PATHS = [
  '/auth', '/catalog', '/pricing', '/locations', '/stock', '/shifts',
  '/suppliers', '/purchase-orders', '/purchase-receipts', '/customers',
  '/users', '/config', '/settings', '/accounts', '/health',
  // Lo que monta el motor bajo `/api` (ventas, medios de pago, config, resguardo).
  '/api',
]
// `/sales` se retiró entero en F4 (2026-09-15, DECISIONS.md ADR-025) -- sin
// backend que lo sirva, ya no tiene nada que hacer en esta lista.

// Las claves del proxy se emiten como regex (Vite trata como RegExp toda
// clave que empieza con `^`) que exige que el path TERMINE ahi o siga con
// `/`. Con el match por prefijo simple que habia antes, una ruta de la SPA
// que empieza igual que un prefijo de la API quedaba secuestrada por el
// proxy y el navegador recibia el JSON del backend en vez de la pagina:
// pasaba con `/catalogo` (capturada por `/catalog`) y con `/config-arca`
// (capturada por `/config`), y solo se notaba al abrir esas URLs directo
// (F5, link pegado), no navegando por el menu.
//
// Es la misma clase de colision documentada en el estandar de la familia
// (ver wiki/concepts/estandares-desarrollo.md y Gestiolibra ADR-023), pero
// por prefijo en vez de por nombre exacto -- por eso no alcanzaba con
// revisar que ninguna ruta se llamara igual que un endpoint. Produccion
// nunca estuvo afectada: ahi sirve FastAPI, que matchea rutas exactas y
// deja caer `/catalogo` al catch-all de la SPA.
const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Dos rutas del backend (F4, 2026-09-15, ADR-025: `app/routers/
// ventas_extra.py`) cuelgan de un prefijo que TAMBIÉN es una pantalla de la
// SPA -- `/ventas` (el listado/detalle) y `/pos` (el mostrador). Un proxy por
// PREFIJO como el de `API_PATHS` las secuestraría: es la MISMA colisión que
// el comentario de arriba documenta para `/catalog`/`/catalogo`, ahora contra
// las propias pantallas de este producto en vez de una ajena -- `/ventas/5`
// (el detalle de una venta) o `/pos` a secas irían al backend, que no tiene
// esas rutas, y el navegador vería un 404 de FastAPI en vez de la SPA.
//
// Por eso van con un patrón tan angosto como la ruta real del backend, no
// por prefijo: sólo `/ventas/<id>/ticket`, `/ventas/<id>/devuelto` y
// `/pos/mp-estado` se proxian; `/ventas`, `/ventas/<id>` y `/pos` a secas
// caen en el catch-all de la SPA, que es lo que tienen que hacer.
const RUTAS_PROPIAS_DEL_BACKEND: Record<string, { target: string; changeOrigin: boolean }> = {
  '^/ventas/\\d+/(?:ticket|devuelto)$': { target: 'http://localhost:8000', changeOrigin: true },
  '^/pos/mp-estado$': { target: 'http://localhost:8000', changeOrigin: true },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      ...Object.fromEntries(
        API_PATHS.map((apiPath) => [
          `^${escapeRegex(apiPath)}(?:/|$)`,
          { target: 'http://localhost:8000', changeOrigin: true },
        ]),
      ),
      ...RUTAS_PROPIAS_DEL_BACKEND,
    },
  },
})
