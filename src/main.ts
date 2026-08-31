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
 *
 * ComfyUI_frontend built-in palettes (coreColorPalettes.ts):
 *   dark, light, solarized, arc, nord, github
 * Only "light" has light_theme: true; all others are dark.
 * This approach does NOT depend on ComfyUI's DOM class names or PrimeVue's
 * darkModeSelector CSS matching, making it immune to future version changes.
 */
function syncThemeClass(container: HTMLElement) {
  const palette =
    app.ui?.settings.getSettingValue<string>('Comfy.ColorPalette') ?? 'dark'
  const isDark = palette !== 'light'
  container.classList.toggle('mm-dark', isDark)
  container.classList.toggle('mm-light', !isDark)
}

/**
 * Runtime CSS scoping (the core isolation mechanism).
 *
 * Both the extension's bundled stylesheet (injected by vite-plugin-css-inject)
 * and PrimeVue's runtime-injected theme stylesheets contain GLOBAL selectors
 * (.p-button, .flex, :root { --mm-* }, ...) that would otherwise leak into
 * ComfyUI's own DOM (which uses the same class names).
 *
 * Every stylesheet that belongs to the extension is therefore rewritten using
 * CSS nesting so that ALL of its rules only apply inside #comfyui-model-manager.
 * This makes the extension fully isolated regardless of PrimeVue or
 * ComfyUI_frontend versions, and fixes both:
 *  - the extension rendering in light mode (variables lost/overridden), and
 *  - ComfyUI's own UI being polluted by the extension's styles.
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

function installStyleScoper() {
  document.head.querySelectorAll('style').forEach((s) => {
    if (isExtensionStyle(s as HTMLStyleElement)) {
      scopeStyle(s as HTMLStyleElement)
    }
  })

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

  observer.observe(document.head, {
    childList: true,
    subtree: true,
    characterData: true,
  })
}

/**
 * Wrap PrimeVue's Tooltip directive so that tooltip elements are appended
 * inside the extension container (instead of document.body). This keeps them
 * inside the scoped CSS region so they remain styled.
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

function createVueApp(rootContainer: string | HTMLElement, container: HTMLElement) {
  const vueApp = createApp(App)
  vueApp.directive('tooltip', createScopedTooltipDirective(container))
  vueApp
    .use(PrimeVue, {
      theme: {
        preset: ComfyUIPreset,
        options: {
          // Custom prefix: extension variables become --mm-*, never colliding
          // with ComfyUI's own --p-* variables. Also used by the style scoper
          // to detect PrimeVue-injected stylesheets that belong to us.
          prefix: 'mm',
          // NOTE: cssLayer is intentionally NOT used. Enabling it triggers a
          // known PrimeVue bug where CSS variables of dynamically rendered
          // components are never injected (primefaces/primevue#8126, still
          // open). Isolation is instead achieved by the runtime style scoper.
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

    // Apply the correct theme class before mounting Vue
    syncThemeClass(container)

    // Re-sync whenever the user changes the palette in ComfyUI settings
    try {
      app.ui?.settings.addEventListener('Comfy.ColorPalette.changed', () => {
        syncThemeClass(container)
      })
    } catch (e) {
      console.warn('Model Manager Neo: failed to listen palette changes:', e)
    }

    // Install the runtime CSS scoper BEFORE PrimeVue injects its styles
    installStyleScoper()

    createVueApp(container, container)
  },
})
