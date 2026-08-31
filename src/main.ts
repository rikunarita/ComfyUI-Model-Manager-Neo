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

// PrimeVueのAuraテーマを拡張し、プライマリーカラーをComfyUIと一致させる
const ComfyUIPreset = definePreset(Aura, {
  semantic: {
    primary: Aura['primitive'].blue,
  },
})

function createVueApp(rootContainer: string | HTMLElement) {
  const vueApp = createApp(App)
  // Tooltipディレクティブは、Neo版独自のスコープ化処理を回避して、PrimeVueの標準機能をそのまま利用する
  vueApp.directive('tooltip', Tooltip)
  vueApp
    .use(PrimeVue, {
      theme: {
        preset: ComfyUIPreset,
        options: {
          // Neo版独自のプレフィックスを維持することで、ComfyUI本体の.p-*クラスとの衝突を回避する
          prefix: 'mm',
          // カスケードレイヤーを有効化。これにより、拡張機能のCSSは常に本体のCSSより後に適用されるが、優先度は低い。
          // PrimeVueのドキュメントでは、styled modeでTailwindと併用する場合、このオプションを有効にする必要があるとされている[[83]]
          cssLayer: 'auto',
          // ComfyUI本体のダークモードセレクタに合わせる。これにより、本体のダークモード設定が管理者UIにも自動反映される。
          // Neo版独自の.mm-darkクラスを付与するsyncThemeClass()関数は不要になった。
          darkModeSelector: '.dark-theme, :root:has(.dark-theme)',
        },
      },
    })
    .use(ToastService)
    .use(ConfirmationService)
    .use(i18n)
    .mount(rootContainer)
}

// ComfyUIエクステンション登録API
app.registerExtension({
  name: 'Comfy.ModelManager',
  // 公式のTopbarメニューAPIに対応
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
