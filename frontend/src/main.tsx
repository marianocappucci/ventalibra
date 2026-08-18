import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './context/AuthContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)

// Instalable como aplicación: el service worker no cachea nada (ver
// `public/sw.js`), sólo existe para que el navegador ofrezca instalarla.
// El fallo se traga a propósito: que no se pueda registrar —contexto sin
// https, un navegador que no lo soporta— no tiene por qué romper la app.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
