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
  // スコープ化ディレクティブを廃止し、標準のTooltipを使用
  // レイヤー隔離により、body直下にテレポートされても正しくスタイルが適用される
  vueApp.directive('tooltip', Tooltip)
  vueApp
    .use(PrimeVue, {
      theme: {
        preset: ComfyUIPreset,
        options: {
          prefix: 'mm',
          // CSSレイヤーを有効化。style.cssで定義したレイヤー順序と整合させる
          cssLayer: {
            name: 'mm-primevue',
            order: 'mm-tailwind-base, mm-primevue, mm-tailwind-utilities',
          },
          // ComfyUI本体のダークモードクラスに追従
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

    // syncThemeClass, installStyleScoper 等は全て不要になったため削除
    createVueApp(container)
  },
})
