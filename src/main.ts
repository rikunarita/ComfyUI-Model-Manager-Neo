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

function createVueApp(rootContainer: string | HTMLElement) {
  const vueApp = createApp(App)
  vueApp.directive('tooltip', Tooltip)
  vueApp
    .use(PrimeVue, {
      theme: {
        preset: ComfyUIPreset,
        options: {
          // Neoの独自機能を維持（ComfyUI本体の .p-* との衝突回避）
          prefix: 'mm',
          // カスケードレイヤーを有効化。レイヤードCSSはアンレイヤード（ComfyUI本体）に
          // 常に勝たないため、Tailwindユーティリティのグローバル漏洩が原理的に起きなくなる。
          cssLayer: {
            name: 'mm-primevue',
            order: 'mm-tailwind-base, mm-primevue, mm-tailwind-utilities',
          },
          // ComfyUIの公式ルートクラスに追従。Neo独自の mm-dark/mm-light は不要。
          darkModeSelector: '.dark-theme, :root:has(.dark-theme)',
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

    createVueApp(container)
  },
})
