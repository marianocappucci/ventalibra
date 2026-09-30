import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './context/AuthContext'
import { REDIRECCIONES_DE_CATALOGO, REDIRECCIONES_DE_CONFIGURACION, REDIRECCIONES_DEL_KIT } from './rutas-viejas'
import { Layout } from './components/Layout'
import { ModulosContext, modulosDe } from './lib/modulos'
import { type Capacidad, inicioDe, puede } from './lib/permisos'
import { Login } from './pages/Login'
import { ForgotPassword, ResetPassword } from './pages/PasswordReset'
import { Pos } from './pages/Pos'
import { Productos } from './pages/Productos'
import { ListasPrecio } from './pages/ListasPrecio'
import { ListaPrecioDetalle } from './pages/ListaPrecioDetalle'
import { ActualizacionMasivaPrecios } from 'libra-ui/comercio/ActualizacionMasivaPrecios'
import { Promociones } from 'libra-ui/comercio/Promociones'
import { EtiquetasGondola } from 'libra-ui/comercio/EtiquetasGondola'
import { Stock } from './pages/Stock'
import { Sucursales } from './pages/Sucursales'
import { SucursalDetalle } from './pages/SucursalDetalle'
import { DepositoDetalle } from './pages/DepositoDetalle'
import { Transferencias } from './pages/Transferencias'
import { Cajas } from './pages/Cajas'
import { CierreDiario } from './pages/CierreDiario'
import { Turnos } from './pages/Turnos'
import { TurnoCerrar } from 'libra-ui/comercio/TurnoCerrar'
import { TurnoDetalle } from 'libra-ui/comercio/TurnoDetalle'
import { Proveedores } from './pages/Proveedores'
import { ProveedorDetalle } from './pages/ProveedorDetalle'
import { Compras } from 'libra-ui/comercio/Compras'
import { CompraDetalle } from 'libra-ui/comercio/CompraDetalle'
import { Clientes } from './pages/Clientes'
import { ClienteDetalle } from './pages/ClienteDetalle'
import { Usuarios } from './pages/Usuarios'
import { Configuracion } from './pages/Configuracion'
import { CuentasCorrientes } from './pages/CuentasCorrientes'
import { CuentaCorrienteDetalle } from './pages/CuentaCorrienteDetalle'
import { Tesoreria } from 'libra-ui/comercio/Tesoreria'
import { TesoreriaDetalle } from 'libra-ui/comercio/TesoreriaDetalle'
import { Egresos } from 'libra-ui/comercio/Egresos'
import { EgresoDetalle } from 'libra-ui/comercio/EgresoDetalle'
import { LibrosIva } from 'libra-ui/comercio/LibrosIva'
import { Ventas } from './pages/Ventas'
import { VentaDetalle } from './pages/VentaDetalle'
import { Reportes } from './pages/Reportes'
import { Margen } from './pages/Margen'
import { Reposicion } from './pages/Reposicion'
import { Dashboard } from './pages/Dashboard'
import { CajaPorMedio } from './pages/CajaPorMedio'
import { Logs } from './pages/Logs'

// `cap`: la capacidad (o cualquiera de una lista) que pide la ruta (`lib/permisos.ts`, ADR-049). Sin `cap` alcanza con
// estar en sesión. Quien no la tiene va a su pantalla inicial (el POS si vende, el stock si es del depósito) y, si su
// rol no tiene ninguna de las dos, ve el aviso de abajo: nunca una redirección en círculo. Sólo decide qué se ofrece;
// el que corta es el backend.
// Sucursales y depósitos: los ve quien administra la estructura o quien mueve mercadería entre depósitos.
const SUCURSALES: readonly Capacidad[] = ['sucursales.admin', 'stock.transferir']

function ProtectedRoute({ children, cap }: { children: ReactNode; cap?: Capacidad | readonly Capacidad[] }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Cargando…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (cap && !puede(user, cap)) {
    const inicio = inicioDe(user)
    if (inicio) return <Navigate to={inicio} replace />
    return (
      <div className="flex min-h-svh items-center justify-center p-6 text-center text-sm text-muted-foreground">
        Tu usuario no tiene pantallas asignadas. Pedile a un administrador que le asigne un rol.
      </div>
    )
  }
  // Los módulos del plan que la SPA lee para ofrecer (o no) lo que es de Premium; ver `lib/modulos.ts`.
  return (
    <ModulosContext.Provider value={modulosDe(user)}>
      <Layout>{children}</Layout>
    </ModulosContext.Provider>
  )
}

// La raíz y toda ruta desconocida: a la pantalla inicial del rol (POS o stock), o al login si no hay sesión.
function Inicio() {
  const { user, loading } = useAuth()
  if (loading) return null
  return <Navigate to={user ? (inicioDe(user) ?? '/pos') : '/login'} replace />
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
          <ProtectedRoute cap="ventas.pos">
            <Pos />
          </ProtectedRoute>
        }
      />
      <Route
        path="/productos"
        element={
          <ProtectedRoute cap="catalogo.ver">
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
          <ProtectedRoute cap="compras.ver">
            <Compras />
          </ProtectedRoute>
        }
      />
      <Route
        path="/compras/:id"
        element={
          <ProtectedRoute cap="compras.ver">
            <CompraDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/proveedores"
        element={
          <ProtectedRoute cap="compras.ver">
            <Proveedores />
          </ProtectedRoute>
        }
      />
      <Route
        path="/proveedores/:id"
        element={
          <ProtectedRoute cap="compras.ver">
            <ProveedorDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/clientes"
        element={
          <ProtectedRoute cap="clientes.ver">
            <Clientes />
          </ProtectedRoute>
        }
      />
      <Route
        path="/clientes/:id"
        element={
          <ProtectedRoute cap="clientes.ver">
            <ClienteDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/ventas"
        element={
          <ProtectedRoute cap="ventas.pos">
            <Ventas />
          </ProtectedRoute>
        }
      />
      <Route
        path="/ventas/:id"
        element={
          <ProtectedRoute cap="ventas.pos">
            <VentaDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cuentas-corrientes"
        element={
          <ProtectedRoute cap="cuenta_corriente">
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
          <ProtectedRoute cap="cuenta_corriente">
            <CuentaCorrienteDetalle />
          </ProtectedRoute>
        }
      />
      {/* Quien mueve la mercadería entre locales es el encargado o el depósito, no el dueño (decisión del humano,
          2026-09-21; `stock.transferir`). El alta de sucursales sí es admin (`sucursales.admin`) -- esa cambia la
          estructura de la instancia, esto mueve existencias. */}
      {/* Mirar cuánto hay es de todos los roles (`stock.ver`), el depósito incluido. */}
      <Route
        path="/stock"
        element={
          <ProtectedRoute cap="stock.ver">
            <Stock />
          </ProtectedRoute>
        }
      />
      <Route
        path="/transferencias"
        element={
          <ProtectedRoute cap="stock.transferir">
            <Transferencias />
          </ProtectedRoute>
        }
      />
      <Route
        path="/sucursales"
        element={
          <ProtectedRoute cap={SUCURSALES}>
            <Sucursales />
          </ProtectedRoute>
        }
      />
      <Route
        path="/sucursales/:id"
        element={
          <ProtectedRoute cap={SUCURSALES}>
            <SucursalDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/depositos/:id"
        element={
          <ProtectedRoute cap={SUCURSALES}>
            <DepositoDetalle />
          </ProtectedRoute>
        }
      />
      <Route
        path="/listas-precio"
        element={
          <ProtectedRoute cap="precios.escribir">
            <ListasPrecio />
          </ProtectedRoute>
        }
      />
      <Route
        path="/listas-precio/:id"
        element={
          <ProtectedRoute cap="precios.escribir">
            <ListaPrecioDetalle />
          </ProtectedRoute>
        }
      />
      {/* Actualización masiva de precios (roadmap de producto, 2026-09-28): la pantalla del kit sin wrapper, sin
          variantes que apagar -- mismo caso que Compras/Tesoreria. */}
      <Route
        path="/actualizacion-masiva-precios"
        element={
          <ProtectedRoute cap="precios.escribir">
            <ActualizacionMasivaPrecios />
          </ProtectedRoute>
        }
      />
      {/* Promociones (roadmap de producto, 2026-09-28, ADR-043): «llevá N pagá M» y combos. La pantalla del
          kit sin wrapper; las reglas las carga el admin, el cajero sólo las ve aplicadas en el POS. */}
      <Route
        path="/promociones"
        element={
          <ProtectedRoute cap="precios.escribir">
            <Promociones />
          </ProtectedRoute>
        }
      />
      {/* Etiquetas de góndola (roadmap de producto, 2026-09-29, ADR-047): la pantalla del kit sin wrapper, de sólo
          lectura sobre productos y listas de precio. Del admin y el encargado (`etiquetas`). */}
      <Route
        path="/etiquetas"
        element={
          <ProtectedRoute cap="etiquetas">
            <EtiquetasGondola />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cajas"
        element={
          <ProtectedRoute cap="caja.admin">
            <Cajas />
          </ProtectedRoute>
        }
      />
      {/* Tesorería (fase 10, ADR-037): cuentas bancarias y transferencias, sin ganchos ni variantes. */}
      <Route
        path="/tesoreria"
        element={
          <ProtectedRoute cap="tesoreria">
            <Tesoreria />
          </ProtectedRoute>
        }
      />
      <Route
        path="/tesoreria/:id"
        element={
          <ProtectedRoute cap="tesoreria">
            <TesoreriaDetalle />
          </ProtectedRoute>
        }
      />
      {/* Egresos (fase 11, ADR-038): de `egresos` (encargado, y el staff heredado además del admin). */}
      <Route path="/egresos" element={<ProtectedRoute cap="egresos"><Egresos /></ProtectedRoute>} />
      <Route path="/egresos/:id" element={<ProtectedRoute cap="egresos"><EgresoDetalle /></ProtectedRoute>} />
      {/* Libros IVA (fase 12, ADR-038): contable-fiscal, de `libros_iva` (admin y encargado). */}
      <Route
        path="/libros-iva"
        element={
          <ProtectedRoute cap="libros_iva">
            <LibrosIva />
          </ProtectedRoute>
        }
      />
      {/* Turnos de caja (ADR-032): cada uno ve los suyos; el encargado y el admin, los de todos (`turnos.todos`). */}
      <Route path="/turnos" element={<ProtectedRoute cap="caja.propia"><Turnos /></ProtectedRoute>} />
      <Route path="/turnos/:id" element={<ProtectedRoute cap="caja.propia"><TurnoDetalle /></ProtectedRoute>} />
      <Route path="/turnos/:id/cerrar" element={<ProtectedRoute cap="caja.propia"><TurnoCerrar /></ProtectedRoute>} />
      {/* El cierre diario es del encargado y del admin (`cierre_diario`; el staff heredado lo sigue teniendo). El
          cajero nuevo ya no: ADR-049. */}
      <Route
        path="/cierre-diario"
        element={
          <ProtectedRoute cap="cierre_diario">
            <CierreDiario />
          </ProtectedRoute>
        }
      />
      <Route
        path="/usuarios"
        element={
          <ProtectedRoute cap="usuarios.admin">
            <Usuarios />
          </ProtectedRoute>
        }
      />
      {/* Una sola ruta para las seis secciones: la activa va en `?seccion=`,
          así se puede linkear una en particular sin multiplicar rutas. */}
      <Route
        path="/configuracion"
        element={
          <ProtectedRoute cap="config">
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
        path="/dashboard"
        element={
          <ProtectedRoute cap="dashboard">
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reportes"
        element={
          <ProtectedRoute cap="reportes">
            <Reportes />
          </ProtectedRoute>
        }
      />
      <Route
        path="/margen"
        element={
          <ProtectedRoute cap="margen">
            <Margen />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reposicion"
        element={
          <ProtectedRoute cap="reposicion.ver">
            <Reposicion />
          </ProtectedRoute>
        }
      />
      <Route
        path="/caja-medios"
        element={
          <ProtectedRoute cap="reportes">
            <CajaPorMedio />
          </ProtectedRoute>
        }
      />
      {/* El gateo real es del backend (capacidad `logs` sobre `/logs`). */}
      <Route
        path="/logs"
        element={
          <ProtectedRoute cap="logs">
            <Logs />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Inicio />} />
    </Routes>
  )
}
