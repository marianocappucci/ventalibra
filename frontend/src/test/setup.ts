import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Los `findBy*` y `waitFor` esperan 1 s por defecto, y las pantallas de este
// producto montan el `App` entero (menu lateral, auth, kit de libra-ui) antes
// de pedir los datos: aun con la maquina libre tardan ~0,5 s en aparecer, y
// con la suite completa en paralelo (un worker por core) o un CI cargado
// pasan de 1 s con el elemento YA en camino. El tope no vuelve lento al test
// que anda -- `findBy` devuelve apenas aparece --, solo da margen al que
// espera; un elemento que de verdad no esta sigue fallando, 5 s despues.
configure({ asyncUtilTimeout: 5000 })

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// jsdom no implementa estas tres APIs y los componentes de shadcn (que
// usan Radix por debajo) las tocan al montar. Sin los polyfills, cualquier
// pantalla con un Select o un Dialog revienta con un TypeError que no
// tiene nada que ver con lo que se esta probando.
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }),
  })
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn()
}

// La captura de puntero, que jsdom tampoco implementa. El `Select` de Radix la
// llama al abrirse: sin esto el menú **nunca se despliega** y el test falla con
// "unable to find role=option", que parece un selector mal escrito y no lo es.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
}

// jsdom NO tiene motor de layout: implementa `document.createRange()` pero
// el Range que devuelve no trae `getBoundingClientRect`. El `data-table`
// de libra-ui mide ahi el ancho de la columna de acciones y revienta con
// un TypeError en un layout effect.
//
// Se pone un polyfill en vez de tocar libra-ui: en jsdom cualquier medicion
// da cero igual, asi que saltearla en el componente daria exactamente el
// mismo resultado, pero cambiando codigo compartido por seis productos para
// acomodar al entorno de tests.
if (typeof Range !== 'undefined' && !Range.prototype.getBoundingClientRect) {
  const cero = () => ({
    x: 0, y: 0, width: 0, height: 0, top: 0, right: 0, bottom: 0, left: 0,
    toJSON: () => ({}),
  }) as DOMRect
  Range.prototype.getBoundingClientRect = cero
  Range.prototype.getClientRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList
}
