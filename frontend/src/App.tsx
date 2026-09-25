import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './context/AuthContext'
import { REDIRECCIONES_DE_CATALOGO, REDIRECCIONES_DE_CONFIGURACION, REDIRECCIONES_DEL_KIT } from './rutas-viejas'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { ForgotPassword, ResetPassword } from './pages/PasswordReset'
import { Pos } from './pages/Pos'
import { Productos } from './pages/Productos'
import { Stock } from './pages/Stock'
import { Sucursales } from './pages/Sucursales'
import { Transferencias } from './pages/Transferencias'
import { Cajas } from './pages/Cajas'
import { CierreDiario } from './pages/CierreDiario'
import { Proveedores } from './pages/Proveedores'
import { Compras } from './pages/Compras'
import { CompraDetalle } from './pages/CompraDetalle'
import { Clientes } from './pages/Clientes'
import { ClienteDetalle } from './pages/ClienteDetalle'
import { Usuarios } from './pages/Usuarios'
import { Configuracion } from './pages/Configuracion'
import { CuentasCorrientes } from './pages/CuentasCorrientes'
import { CuentaCorrienteDetalle } from './pages/CuentaCorrienteDetalle'
import { Ventas } from './pages/Ventas'
import { VentaDetalle } from './pages/VentaDetalle'
import { Reportes } from './pages/Reportes'
import { Logs } from './pages/Logs'

function ProtectedRoute({ children, adminOnly = false }: { children: ReactNode; adminOnly?: boolean }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Cargando…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (adminOnly && user.role !== 'admin') return <Navigate to="/pos" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Públicas a propósito: quien las necesita no puede iniciar sesión. */}
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route
        path="/pos"
        element={
          <ProtectedRoute>
            <Pos />
          </ProtectedRoute>
        }
      />
      <Route
        path="/productos"
        element={
          <ProtectedRoute>
            <Productos />
          </ProtectedRoute>
        }
      />
      {/* `/catalogo` era el ítem del menú antes de renombrarse a Productos
          (2026-09-17). Redirige en vez de borrarse: puede estar en un
          favorito o en un mensaje -- mismo criterio que
          REDIRECCIONES_DE_CONFIGURACION, ver el docstring de ese archivo. */}
      {Object.entries(REDIRECCIONES_DE_CATALOGO).map(([desde, hacia]) => (
        <Route key={desde} path={desde} element={<Navigate to={hacia} replace />} />
      ))}
      <Route
        path="/compras"
        element={
          <ProtectedRoute>
            <Compras />
          </ProtectedRoute>
        }
      />
      <Route
        path="/compras/:id"
        element={
          <ProtectedRoute>
            <CompraDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/proveedores"
        element={
          <ProtectedRoute>
            <Proveedores />
          </ProtectedRoute>
        }
      />
      <Route
        path="/clientes"
        element={
          <ProtectedRoute>
            <Clientes />
          </ProtectedRoute>
        }
      />
      <Route
        path="/clientes/:id"
        element={
          <ProtectedRoute>
            <ClienteDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/ventas"
        element={
          <ProtectedRoute>
            <Ventas />
          </ProtectedRoute>
        }
      />
      <Route
        path="/ventas/:id"
        element={
          <ProtectedRoute>
            <VentaDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cuentas-corrientes"
        element={
          <ProtectedRoute>
            <CuentasCorrientes />
          </ProtectedRoute>
        }
      />
      {/* La lista del kit linkea `/cuenta-corriente/:id` (Ver cuenta); su
          detalle vuelve a `/cuenta-corriente` y linkea `/clientes/:id`
          (Ficha cliente). Esas dos redirigen -- van en la tabla
          `REDIRECCIONES_DEL_KIT` de `rutas-viejas.ts`, junto a las demás. */}
      <Route
        path="/cuenta-corriente/:id"
        element={
          <ProtectedRoute>
            <CuentaCorrienteDetalle />
          </ProtectedRoute>
        }
      />
      {/* Staff o admin (decisión del humano, 2026-09-21): quien mueve la
          mercadería entre locales es el encargado, no el dueño. El alta de
          sucursales sí es admin -- esa cambia la estructura de la instancia,
          esto mueve existencias. */}
      {/* Mirar cuánto hay es del mostrador, como el POS: sin `adminOnly`. */}
      <Route
        path="/stock"
        element={
          <ProtectedRoute>
            <Stock />
          </ProtectedRoute>
        }
      />
      <Route
        path="/transferencias"
        element={
          <ProtectedRoute>
            <Transferencias />
          </ProtectedRoute>
        }
      />
      <Route
        path="/sucursales"
        element={
          <ProtectedRoute>
            <Sucursales />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cajas"
        element={
          <ProtectedRoute adminOnly>
            <Cajas />
          </ProtectedRoute>
        }
      />
      {/* Admin y cajero (staff): el cierre diario lo puede hacer cualquiera
          de los dos -- ver DECISIONS.md, la feature de cajas por sucursal. */}
      <Route
        path="/cierre-diario"
        element={
          <ProtectedRoute>
            <CierreDiario />
          </ProtectedRoute>
        }
      />
      <Route
        path="/usuarios"
        element={
          <ProtectedRoute adminOnly>
            <Usuarios />
          </ProtectedRoute>
        }
      />
      {/* Una sola ruta para las seis secciones: la activa va en `?seccion=`,
          así se puede linkear una en particular sin multiplicar rutas. */}
      <Route
        path="/configuracion"
        element={
          <ProtectedRoute adminOnly>
            <Configuracion />
          </ProtectedRoute>
        }
      />
      {/* El "Volver" del kit (`libra-ui/comercio/CuentaCorriente*`) apunta
          a `/cuenta-corriente`; se redirige a la lista. Su link de "Ficha
          cliente" ahora tiene ruta propia arriba, en `/clientes/:id`.

          Las tablas viven en `rutas-viejas.ts` para que el guard de títulos
          (y los tests) no midan una copia distinta de la que la app usa --
          ver el docstring de ese archivo. En particular, un `<Route
          path="...">` literal con `<Navigate>` adentro hace que el auditor
          le atribuya al path la PRIMERA pantalla vecina. */}
      {Object.entries(REDIRECCIONES_DE_CONFIGURACION).map(([desde, hacia]) => (
        <Route key={desde} path={desde} element={<Navigate to={hacia} replace />} />
      ))}
      {Object.entries(REDIRECCIONES_DEL_KIT).map(([desde, hacia]) => (
        <Route key={desde} path={desde} element={<Navigate to={hacia} replace />} />
      ))}
      <Route
        path="/reportes"
        element={
          <ProtectedRoute adminOnly>
            <Reportes />
          </ProtectedRoute>
        }
      />
      {/* El gateo real es del backend (`admin_only` sobre `/logs`). */}
      <Route
        path="/logs"
        element={
          <ProtectedRoute adminOnly>
            <Logs />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/pos" replace />} />
    </Routes>
  )
}
