import { onBeforeMount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { request } from 'hooks/request'
import { defineStore } from 'hooks/store'
import { useToast } from 'hooks/toast'
import { api } from 'scripts/comfyAPI'

/**
 * Global batch-scan state.
 *
 * BUG FIX: the `update_scan_information_task` listener used to live inside the
 * DialogScanning component (registered on mount, removed on unmount). Scan
 * results that arrived while the dialog was closed — or after a websocket gap
 * caused by the (previously loop-blocking) scan work — were silently dropped,
 * so "the results never reached the browser".
 *
 * The listeners now live in an app-lifetime store (registered once on app
 * mount, like the download-task listeners), the state survives dialog
 * re-opens, an explicit completion event finalises the scan with a toast +
 * model refresh, and a `reconnected` hook re-syncs from the server.
 */
export const useScan = defineStore('scan', store => {
  const { toast } = useToast()
  const { t } = useI18n()

  /** Absolute model path -> information downloaded (shared across re-opens). */
  const scanModels = ref<Record<string, boolean>>({})

  const notifyCompleted = (finalModels?: Record<string, boolean>) => {
    if (finalModels) {
      scanModels.value = finalModels
    }
    toast.add({
      severity: 'success',
      summary: 'Success',
      detail: t('scanCompleted'),
      life: 3000,
    })
    // Make the results visible: refresh the model lists so freshly downloaded
    // previews/descriptions show up without a manual refresh.
    store.models.refresh().catch(() => {})
  }

  /**
   * Pull the current task state from the server.
   * Returns the models map while a task file exists, otherwise `null`.
   */
  const syncFromServer = async (): Promise<Record<string, boolean> | null> => {
    try {
      const result = await request('/model-info/scan')
      const listContent = result?.models ?? null
      if (listContent) {
        scanModels.value = listContent
        return listContent
      }
      // The task file is gone: a scan that still had pending entries finished
      // while no live listener was attached (dialog closed / websocket gap).
      const entries = Object.keys(scanModels.value)
      const hadPending = entries.length > 0 && Object.values(scanModels.value).some(v => !v)
      if (hadPending) {
        const done = Object.fromEntries(entries.map(key => [key, true]))
        notifyCompleted(done)
      } else {
        scanModels.value = {}
      }
      return null
    } catch {
      return null
    }
  }

  onBeforeMount(() => {
    api.addEventListener('update_scan_information_task', (event: CustomEvent) => {
      scanModels.value = event.detail?.models ?? {}
    })

    api.addEventListener('complete_scan_information_task', (event: CustomEvent) => {
      notifyCompleted(event.detail?.models)
    })

    api.addEventListener('reconnected', () => {
      // Recover progress after a websocket interruption.
      syncFromServer()
    })
  })

  return { scanModels, syncFromServer }
})

declare module 'hooks/store' {
  interface StoreProvider {
    scan: ReturnType<typeof useScan>
  }
}
