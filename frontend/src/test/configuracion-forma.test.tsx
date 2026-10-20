// La FORMA de la pantalla de Configuración de este producto.
//
// La pantalla la rinde `libra-ui/Configuracion`, que tiene sus propios tests:
// lo que se prueba acá es **lo que declara VentaLibra**, que es lo único que
// vive en este repo y lo único que puede divergir del resto de la familia sin
// que nadie lo note.
//
// Dos declaraciones que si se escriben mal no rompen nada y arruinan la
// pantalla igual:
//
//  1. 🔴 **`webhook: false`.** Este producto NO tiene webhook de MercadoPago, y
//     está medido: en la instancia real del cliente no llegó ni un `POST` a
//     `/webhooks/mercadopago` —cero contra cinco al endpoint del poll— y el
//     cobro se resuelve poleando. Mostrar el campo del Webhook Secret manda al
//     comercio a configurar algo que no hace nada.
//  2. 🔴 **El slug de la empresa de ARCA.** `services/billing.py` lee la
//     configuración de facturación con `EMPRESA = "venta"`. En una instancia
//     sin fila, el primer guardado la crea: si la crea como `default`, ese
//     servicio no la lee nunca.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CLAVE_DE_LA_SECCION, TEXTO_SIN_ADICIONAL } from 'libra-ui/SucursalSinInternet'

import { ModulosContext } from '../lib/modulos'
import { Configuracion } from '../pages/Configuracion'
import { REDIRECCIONES_DE_CONFIGURACION } from '../rutas-viejas'

// La sesión, cambiable por test: `Configuracion` mira `sucursales.admin` (y no `config`) para ofrecer «Sucursal sin internet».
const sesion = vi.hoisted(() => ({
  capacidades: ['config', 'sucursales.admin'] as string[],
}))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', username: 'u', name: 'U', role: 'admin', capacidades: sesion.capacidades }, loading: false,
  }),
}))

let pedidos: { url: string; metodo: string; cuerpo: unknown }[] = []

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  pedidos = []
  sesion.capacidades = ['config', 'sucursales.admin']
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    pedidos.push({ url: u, metodo, cuerpo: init?.body ?? null })

    // «Sucursal sin internet»: sin el adicional contratado y sin nodos (la instancia común, plan único).
    if (u.includes('/api/nodos-offline')) {
      return Promise.resolve(json({
        producto: 'ventalibra', contratado: false, instalador_url: '', central_url: null, central_url_error: null,
        emisor_faltan: [], emisor_error: null, umbral_minutos: 30, sucursales: [], nodos: [], nodos_activos: 0,
      }))
    }
    if (u.includes('/logo')) return Promise.resolve(new Response('', { status: 404 }))
    if (u.includes('/admin/smtp')) {
      return Promise.resolve(json({
        origen: 'entorno', host: '', port: 587, user: '', from_email: '', from_name: '',
        password_definida: false, password_indescifrable: false, configurado: false,
      }))
    }
    if (u.includes('/api/config/mercadopago')) {
      return Promise.resolve(json({
        mp_access_token: '', mp_access_token_cargado: false,
        mp_webhook_secret: '', mp_webhook_secret_cargado: false,
        mp_concepto_descripcion: '', mp_iva_rate: '0',
        mp_user_id: '', mp_pos_id: '', mp_auto_facturar_ventas: false,
      }))
    }
    if (u.includes('/config/arca/estado')) return Promise.resolve(json({ configurado: false }))
    // Instancia nueva: todavía no hay fila de ARCA.
    if (u.includes('/config/arca')) return Promise.resolve(json(null))
    if (u.includes('/api/config/empresa')) {
      return Promise.resolve(json({
        empresa_nombre: '', empresa_direccion: '', empresa_cuit: '', empresa_telefono: '',
        empresa_email: '', empresa_iibb: '', empresa_iva_condition: 'Monotributista',
        empresa_inicio_actividades: '',
      }))
    }
    return Promise.resolve(json([]))
  }))
})

const montar = (ruta = '/configuracion') =>
  render(<MemoryRouter initialEntries={[ruta]}><Configuracion /></MemoryRouter>)

describe('la Configuración de VentaLibra', () => {
  it('el administrador tiene las pestañas de la familia, las propias del mostrador y «Sucursal sin internet»', async () => {
    montar()

    const pestanias = (await screen.findAllByRole('tab')).map((t) => t.textContent)
    expect(pestanias).toEqual([
      'Empresa', 'Integraciones', 'Balanza', 'Ticket', 'Unidades de medida', 'Categorías', 'Sucursal sin internet',
      'Datos / Backup',
    ])
  })

  it('🔴 un rol con `config` pero sin `sucursales.admin` no ve «Sucursal sin internet»', async () => {
    // Son dos capacidades distintas: entrar a Configuración no alcanza para dar de alta nodos de LibraEdge.
    sesion.capacidades = ['config']
    montar()

    const pestanias = (await screen.findAllByRole('tab')).map((t) => t.textContent)
    expect(pestanias).toEqual([
      'Empresa', 'Integraciones', 'Balanza', 'Ticket', 'Unidades de medida', 'Categorías', 'Datos / Backup',
    ])
    expect(screen.queryByRole('tab', { name: /Sucursal sin internet/ })).toBeNull()
  })

  it('sin `sucursales.admin`, ni pidiéndola por la URL aparece la sección ni se consulta a los nodos', async () => {
    sesion.capacidades = ['config']
    montar(`/configuracion?seccion=${CLAVE_DE_LA_SECCION}`)

    // Cae en la primera (Empresa), como cualquier `?seccion=` que no existe.
    expect(await screen.findByRole('tab', { name: /Empresa/ })).toHaveAttribute('aria-selected', 'true')
    expect(pedidos.some((p) => p.url.includes('/api/nodos-offline'))).toBe(false)
  })

  it('la sección del administrador abre «Sucursal sin internet» con su estado (sin el adicional: cómo contratarlo)', async () => {
    montar(`/configuracion?seccion=${CLAVE_DE_LA_SECCION}`)

    expect(await screen.findByRole('tab', { name: /Sucursal sin internet/ })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText(TEXTO_SIN_ADICIONAL)).toBeInTheDocument()
  })

  it('sin el módulo `facturacion` la sección de LibraEdge sigue estando (las dos variantes se combinan)', async () => {
    render(
      <MemoryRouter initialEntries={['/configuracion']}>
        <ModulosContext.Provider value={['multisucursal']}><Configuracion /></ModulosContext.Provider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('tab', { name: /Sucursal sin internet/ })).toBeInTheDocument()
  })

  it('la ruta vieja `/sucursal-sin-internet` redirige a la clave que usa el kit para la sección', () => {
    expect(REDIRECCIONES_DE_CONFIGURACION['/sucursal-sin-internet'])
      .toBe(`/configuracion?seccion=${CLAVE_DE_LA_SECCION}`)
  })

  it('las tres integraciones están, en la sub-navegación', async () => {
    montar('/configuracion?seccion=integraciones')

    await screen.findAllByRole('tab')
    const navegacion = screen.getAllByRole('button', {
      name: /^(MercadoPago|ARCA \/ AFIP|Email \/ SMTP)$/,
    })
    expect(navegacion.map((b) => b.textContent)).toEqual([
      'MercadoPago', 'ARCA / AFIP', 'Email / SMTP',
    ])
  })

  it('🔴 MercadoPago no pide una firma para un webhook que este producto no tiene', async () => {
    montar('/configuracion?seccion=integraciones&integracion=mercadopago')

    // Los tres datos del QR sí, que son los que el POS necesita…
    expect(await screen.findByLabelText(/Access Token/)).toBeInTheDocument()
    expect(screen.getByLabelText(/User ID \(QR\)/)).toBeInTheDocument()
    expect(screen.getByLabelText(/POS ID \(QR\)/)).toBeInTheDocument()
    // …y nada del webhook, que acá no existe.
    expect(screen.queryByLabelText(/Webhook Secret/)).toBeNull()
    expect(screen.queryByText(/URL del webhook/)).toBeNull()
  })

  it('avisa que el QR no cobra mientras falte alguno de los tres', async () => {
    // Sin el aviso, una caja a medio configurar se descubre recién cuando un
    // cliente escanea el cartel impreso del mostrador y no pasa nada.
    montar('/configuracion?seccion=integraciones&integracion=mercadopago')

    expect(await screen.findByText(/Faltan datos/)).toBeInTheDocument()
  })

  it('🔴 la fila de ARCA se crea con el slug que lee `services/billing.py`', async () => {
    montar('/configuracion?seccion=integraciones&integracion=arca')
    const usuario = userEvent.setup()

    await usuario.click(await screen.findByRole('button', { name: /Guardar ARCA/ }))

    const put = pedidos.find((p) => p.url.includes('/config/arca') && p.metodo === 'PUT')
    expect(put, 'no llegó ningún PUT a /config/arca').toBeTruthy()
    expect(JSON.parse(String(put!.cuerpo)).empresa).toBe('venta')
  })

  it('ARCA sube el certificado: ya no hay dónde tipear una ruta del servidor', async () => {
    montar('/configuracion?seccion=integraciones&integracion=arca&arca=homologacion')

    // 🔑 Se nombra el ambiente: desde libra-ui v0.57.0 la tarjeta muestra los
    // DOS pares de credenciales, así que hay dos "Certificado (.crt)" y dos
    // "Clave privada (.key)" en la misma pantalla. Sin distinguirlos la consulta
    // es ambigua — y además no diría a qué par se refiere.
    expect(await screen.findByLabelText(/Certificado.*Homologaci/))
      .toHaveAttribute('type', 'file')
    expect(screen.getByLabelText(/Clave privada.*Homologaci/))
      .toHaveAttribute('type', 'file')
    // Y el par de producción también está, que es lo que el cambio agrega.
    // Desde libra-ui v0.135.0 (ADR-047) cada ambiente va en su pestaña: el de producción se abre por la URL.
    montar('/configuracion?seccion=integraciones&integracion=arca&arca=produccion')
    expect(await screen.findByLabelText(/Certificado.*Producci/)).toHaveAttribute('type', 'file')
    expect(screen.queryByLabelText(/Path del certificado/)).toBeNull()
  })

  it('los tutoriales nombran a VentaLibra, no al producto del que salió la pantalla', async () => {
    montar('/configuracion?seccion=integraciones&integracion=email')

    expect(await screen.findAllByText(/contraseña de aplicación/)).not.toHaveLength(0)
    expect(screen.getByText('VentaLibra')).toBeInTheDocument()
    expect(screen.queryByText('Contalibra')).toBeNull()
  })

  it('el botón de backup rápido está desde la primera pestaña', async () => {
    montar()

    expect(await screen.findByRole('link', { name: /Backup rápido/ }))
      .toHaveAttribute('href', '/api/config/backup-ahora')
  })
})
