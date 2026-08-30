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
 * Custom palettes may also exist — we treat anything other than "light" as dark.
 *
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

function createVueApp(rootContainer: string | HTMLElement) {
  const vueApp = createApp(App)
  vueApp.directive('tooltip', Tooltip)
  vueApp
    .use(PrimeVue, {
      theme: {
        preset: ComfyUIPreset,
        options: {
          // Custom prefix: extension variables become --mm-*, never colliding
          // with ComfyUI's own --p-* variables.
          prefix: 'mm',
          cssLayer: {
            name: 'primevue',
            order: 'tailwind-base, primevue, tailwind-utilities',
          },
          // Dark mode is driven by the .mm-dark class that syncThemeClass()
          // toggles on the extension container — NOT by ComfyUI's DOM classes.
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
    container.id = 'comfyui-model-manager'
    document.body.appendChild(container)

    // Apply the correct theme class before mounting Vue
    syncThemeClass(container)

    // Re-sync whenever the user changes the palette in ComfyUI settings
    app.ui?.settings.addEventListener('Comfy.ColorPalette.changed', () => {
      syncThemeClass(container)
    })

    createVueApp(container)
  },
})
