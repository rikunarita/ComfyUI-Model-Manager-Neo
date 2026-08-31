import { definePreset } from '@primevue/themes'
import Aura from '@primevue/themes/aura'
import PrimeVue from 'primevue/config'
import ConfirmationService from 'primevue/confirmationservice'
import ToastService from 'primevue/toastservice'
import Tooltip from 'primevue/tooltip'
import { app } from 'scripts/comfyAPI'
import { createApp } from 'vue'
import App from './App.vue'
import { i18n } from './i18n'
import './style.css'

const CONTAINER_ID = 'comfyui-model-manager'

const ComfyUIPreset = definePreset(Aura, {
  semantic: {
    primary: Aura['primitive'].blue,
  },
})

/**
 * Sync the extension's dark/light mode with ComfyUI's active color palette.
 * ComfyUI_frontend built-in palettes: dark, light, solarized, arc, nord, github.
 * Only "light" has light_theme: true; everything else is treated as dark.
 */
function syncThemeClass(container: HTMLElement) {
  const palette =
    app.ui?.settings.getSettingValue<string>('Comfy.ColorPalette') ?? 'dark'
  const isDark = palette !== 'light'
  container.classList.toggle('mm-dark', isDark)
  container.classList.toggle('mm-light', !isDark)
}

/**
 * Runtime CSS scoping (core isolation mechanism).
 * Rewrites every stylesheet that belongs to the extension (detected via
 * data-style-id="model-manager" or the --mm- variable prefix) using CSS
 * nesting, so ALL of its rules only apply inside #comfyui-model-manager.
 * This prevents both:
 *  - the extension leaking styles into ComfyUI (.p-button, tailwind classes),
 *  - ComfyUI leaking its theme into the extension.
 */
let rescoping = false

function scopeCss(css: string): string {
  const cleaned = css.replace(/@layer[^;{]+[;{]/g, '')
  const rewritten = cleaned
    .replaceAll(':root', '&')
    .replaceAll('.mm-dark', '&.mm-dark')
  return `#${CONTAINER_ID}{${rewritten}}`
}

function isExtensionStyle(style: HTMLStyleElement): boolean {
  return (
    style.dataset.styleId === 'model-manager' ||
    (style.textContent?.includes('--mm-') ?? false)
  )
}

function scopeStyle(style: HTMLStyleElement) {
  if (rescoping) return
  const css = style.textContent ?? ''
  if (!css || css.startsWith(`#${CONTAINER_ID}{`)) return
  rescoping = true
  style.textContent = scopeCss(css)
  rescoping = false
}

function scanAndScope() {
  document.querySelectorAll('style').forEach((s) => {
    if (isExtensionStyle(s as HTMLStyleElement)) {
      scopeStyle(s as HTMLStyleElement)
    }
  })
}

function installStyleScoper() {
  scanAndScope()

  // Watch the WHOLE document (some PrimeVue versions inject into body).
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === 'characterData') {
        const parent = mutation.target.parentElement
        if (
          parent &&
          parent.tagName === 'STYLE' &&
          isExtensionStyle(parent as HTMLStyleElement)
        ) {
          scopeStyle(parent as HTMLStyleElement)
        }
      }
      mutation.addedNodes.forEach((node) => {
        if (node instanceof HTMLStyleElement && isExtensionStyle(node)) {
          scopeStyle(node)
        }
      })
    }
  })
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  })

  // Belt-and-suspenders: periodic rescan during startup.
  let count = 0
  const timer = setInterval(() => {
    scanAndScope()
    if (++count >= 10) clearInterval(timer)
  }, 300)
}

/**
 * Wrap PrimeVue's Tooltip directive so tooltip elements are appended inside
 * the extension container and stay within the scoped CSS region.
 */
function createScopedTooltipDirective(container: HTMLElement) {
  const wrap = (binding: any) => {
    const value =
      typeof binding.value === 'object' && binding.value !== null
        ? { ...binding.value }
        : { value: binding.value }
    if (!value.appendTo) value.appendTo = container
    return { ...binding, value }
  }
  const tooltip = Tooltip as any
  return {
    mounted: (el: any, binding: any, vnode: any) =>
      tooltip.mounted?.(el, wrap(binding), vnode),
    updated: (el: any, binding: any, vnode: any) =>
      tooltip.updated?.(el, wrap(binding), vnode),
    unmounted: (el: any, binding: any, vnode: any) =>
      tooltip.unmounted?.(el, binding, vnode),
  }
}

function createVueApp(
  rootContainer: string | HTMLElement,
  container: HTMLElement,
) {
  const vueApp = createApp(App)
  vueApp.directive('tooltip', createScopedTooltipDirective(container))
  vueApp
    .use(PrimeVue, {
      theme: {
        preset: ComfyUIPreset,
        options: {
          // Custom prefix: doubles as the marker for the style scoper and
          // guarantees no --p-* collision with ComfyUI.
          prefix: 'mm',
          // NOTE: cssLayer is intentionally disabled. With PrimeVue >= 4.3,
          // enabling it drops dark-mode/component CSS variables (#8126).
          // Isolation is handled by the runtime scoper instead.
          darkModeSelector: '.mm-dark',
        },
      },
    })
    .use(ToastService)
    .use(ConfirmationService)
    .use(i18n)
    .mount(rootContainer)
}

app.registerExtension({
  name: 'Comfy.ModelManager',
  // 公式 Topbar Menu API への対応
  commands: [
    {
      id: 'Comfy.ModelManager.Open',
      label: 'Model Manager Neo',
      icon: 'pi pi-folder',
      function: () => {
        window.dispatchEvent(new CustomEvent('open-model-manager'))
      },
    },
  ],
  menuCommands: [
    {
      path: ['Extensions'],
      commands: ['Comfy.ModelManager.Open'],
    },
  ],
  setup() {
    const container = document.createElement('div')
    container.id = CONTAINER_ID
    document.body.appendChild(container)

    syncThemeClass(container)

    try {
      app.ui?.settings.addEventListener('Comfy.ColorPalette.changed', () => {
        syncThemeClass(container)
      })
    } catch (e) {
      console.warn('Model Manager Neo: failed to listen palette changes:', e)
    }

    installStyleScoper()

    createVueApp(container, container)
  },
})
