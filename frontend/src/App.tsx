import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './context/AuthContext'
import { REDIRECCIONES_DE_CONFIGURACION } from './rutas-viejas'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { ForgotPassword, ResetPassword } from './pages/PasswordReset'
import { Pos } from './pages/Pos'
import { Catalogo } from './pages/Catalogo'
import { Sucursales } from './pages/Sucursales'
import { Proveedores } from './pages/Proveedores'
import { Compras } from './pages/Compras'
import { Clientes } from './pages/Clientes'
import { Usuarios } from './pages/Usuarios'
import { Configuracion } from './pages/Configuracion'
import { CuentasCorrientes } from './pages/CuentasCorrientes'
import { Ventas } from './pages/Ventas'
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
        path="/catalogo"
        element={
          <ProtectedRoute>
            <Catalogo />
          </ProtectedRoute>
        }
      />
      <Route
        path="/compras"
        element={
          <ProtectedRoute>
            <Compras />
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
        path="/ventas"
        element={
          <ProtectedRoute>
            <Ventas />
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
      <Route
        path="/sucursales"
        element={
          <ProtectedRoute>
            <Sucursales />
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
      {/* Las tres pantallas sueltas pasaron a ser secciones. Se redirigen en
          vez de borrarse: son links que pueden estar en un favorito o en un
          mensaje, y un 404 en Configuración parece que se rompió el sistema.

          La tabla vive en `rutas-viejas.ts` para que el test no pueda medir una
          copia distinta de la que la app usa — ver el docstring de ese
          archivo. */}
      {Object.entries(REDIRECCIONES_DE_CONFIGURACION).map(([desde, hacia]) => (
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
