/** Configuración de VentaLibra.
 *
 *  El armado y las secciones comunes vienen de `libra-ui/Configuracion`, que
 *  desde la v0.47.0 es **la pantalla de Configuración de la familia entera** —
 *  la de Contalibra, con su barra de pestañas, la sub-navegación de
 *  Integraciones, el botón de *Backup rápido* y los tutoriales. Acá se declara
 *  sólo lo que corresponde a este producto.
 *
 *  🔴 **La copia única vive en el kit, no acá.** Es el punto del pedido del
 *  humano del 2026-08-29: *"si hago una modificación en la configuración o una
 *  actualización se actualice en todas"*. Hasta hoy este producto tenía su
 *  propia sección de MercadoPago —`ConfigMercadoPago.tsx`, que se va— con
 *  tres campos, mientras Contalibra tenía otra con siete.
 *
 *  ## Las tres integraciones, y lo que cambió en cada una
 *
 *  - **MercadoPago** lo sirve ahora `libracore.mp_config_router`. Lo que se
 *    gana: el token vuelve **enmascarado** (el endpoint propio lo devolvía en
 *    claro en el JSON de una pantalla), hay un botón que le pregunta a
 *    MercadoPago si el token sirve, y una puerta para desconectar la cuenta.
 *    Las claves de `config.json` son las mismas, así que `mp_qr` y el POS no se
 *    enteran: no hay dato que migrar.
 *  - **ARCA** dejó de pedir un *path del filesystem del servidor* y pasó a
 *    subir el certificado y la clave, validados antes de escribirse, con el
 *    vencimiento a la vista.
 *  - **Correo (SMTP)** suma el tutorial de la contraseña de aplicación de
 *    Gmail, que este producto no tenía.
 *
 *  ## 🔴 `webhook: false` — y no es una simplificación
 *
 *  Este producto **no tiene webhook de MercadoPago**, y está medido: en la
 *  instancia real del cliente no llegó ni un `POST` a `/webhooks/mercadopago`
 *  —cero contra cinco al endpoint del poll— y el cobro se resuelve poleando
 *  (ver `app/services/mp_qr.py`). Mostrarle al comercio el campo del *Webhook
 *  Secret* y la URL sería mandarlo a configurar algo que no hace nada, y
 *  después a buscar por qué "no anda".
 */
import { createConfiguracion } from 'libra-ui/Configuracion'
import { Printer, Scale, Settings } from 'lucide-react'

import { ConfigBalanza } from './ConfigBalanza'
import { ConfigTicket } from './ConfigTicket'

export const Configuracion = createConfiguracion({
  // El icono que el sidebar de este producto le da a /configuracion.
  icono: Settings,
  // Sale en el tutorial de Gmail —es el nombre que hay que ponerle a la
  // contraseña de aplicación— y en el de Padrón A13.
  producto: 'VentaLibra',
  integraciones: {
    // Ver el docstring: acá no hay webhook, y es deliberado.
    mercadopago: { webhook: false },
    // 🔴 `empresa` es el slug de la fila de `arca_config`, el mismo que usa
    // `services/billing.py`. En una instancia sin fila, sin esto el primer
    // guardado la crearía como `default` — donde ese servicio no mira nunca.
    arca: { empresa: 'venta' },
    email: true,
  },
  // Las dos propias. Se quedan en el producto y no suben al kit: la balanza es
  // de un comercio con mostrador y el formato de etiqueta que parsea es
  // específico de acá, y el ticket de este producto no es el de Contalibra.
  propias: [
    { clave: 'balanza', label: 'Balanza', icono: Scale, contenido: <ConfigBalanza /> },
    { clave: 'ticket', label: 'Ticket', icono: Printer, contenido: <ConfigTicket /> },
  ],
})
