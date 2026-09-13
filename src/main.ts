import { createApp } from 'vue'
import { app } from 'scripts/comfyAPI'
import App from './App.vue'
import { ensureLocale, i18n } from './i18n'
import './style.css'

const CONTAINER_ID = 'comfyui-model-manager'

function createVueApp(rootContainer: string | HTMLElement) {
  const vueApp = createApp(App)
  vueApp.use(i18n).mount(rootContainer)
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

    // The active locale bundle is a dynamic import (optimization B-5); mount
    // only once it resolved so the first paint is already translated.
    void ensureLocale(i18n.global.locale.value).finally(() => createVueApp(container))
  },
})
