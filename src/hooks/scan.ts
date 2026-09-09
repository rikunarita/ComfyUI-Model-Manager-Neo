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
 *
 * BUG FIX (ordering): the dialog used to `await` a `GET /model-info/scan` on
 * mount and then unconditionally apply whatever came back. That request is
 * issued *before* the user can press a scan button, so when its response
 * landed after the `POST` that started the scan it described a world where no
 * task existed: it wiped `scanModels`, fired a bogus "scan completed" toast and
 * pushed the dialog back to the type-selection step — where it stayed, because
 * nothing ever moves it to the progress step again. Every mutation now carries
 * a generation stamp and stale HTTP responses are dropped.
 */
export const useScan = defineStore('scan', store => {
  const { toast } = useToast()
  const { t } = useI18n()

  /** Absolute model path -> information downloaded (shared across re-opens). */
  const scanModels = ref<Record<string, boolean>>({})

  /** True while a scan task is known to be running on the server. */
  const scanning = ref(false)

  /** Bumped on every websocket update, so callers can detect a racing push. */
  const updates = ref(0)

  /**
   * Bumped whenever a scan starts or finishes. An in-flight `syncFromServer()`
   * captures it before awaiting and discards its payload if it changed, which
   * is what keeps a slow/stale `GET` from rewinding live progress.
   */
  let generation = 0

  const allDone = (models: Record<string, boolean>) =>
    Object.fromEntries(Object.keys(models).map(key => [key, true]))

  const notifyCompleted = (finalModels?: Record<string, boolean>) => {
    generation++
    scanning.value = false
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

  /** A scan was just started locally (POST) or confirmed by the server. */
  const beginScan = (models?: Record<string, boolean>) => {
    generation++
    scanning.value = true
    if (models) {
      scanModels.value = models
    }
  }

  /** A per-model progress push from the server (always the freshest state). */
  const applyServerUpdate = (models?: Record<string, boolean>) => {
    updates.value++
    scanning.value = true
    scanModels.value = models ?? {}
  }

  /**
   * Pull the current task state from the server.
   * Returns the models map while a task file exists, otherwise `null`.
   */
  const syncFromServer = async (): Promise<Record<string, boolean> | null> => {
    const requestedAt = generation
    try {
      const result = await request('/model-info/scan')
      if (requestedAt !== generation) {
        // A scan started or finished while this request was in flight; the
        // payload is older than what we already know. Report the live state so
        // callers keep showing the progress step.
        return scanModels.value
      }
      const listContent = result?.models ?? null
      if (listContent) {
        scanning.value = true
        scanModels.value = listContent
        return listContent
      }
      // The task file is gone.
      if (scanning.value) {
        // A scan we were tracking finished while no live listener was attached
        // (dialog closed / websocket gap).
        notifyCompleted(allDone(scanModels.value))
        return null
      }
      const entries = Object.keys(scanModels.value)
      const hadPending = entries.length > 0 && Object.values(scanModels.value).some(v => !v)
      if (hadPending) {
        notifyCompleted(allDone(scanModels.value))
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
      applyServerUpdate(event.detail?.models)
    })

    api.addEventListener('complete_scan_information_task', (event: CustomEvent) => {
      notifyCompleted(event.detail?.models)
    })

    api.addEventListener('reconnected', () => {
      // Recover progress after a websocket interruption.
      syncFromServer()
    })
  })

  return { scanModels, scanning, updates, syncFromServer, beginScan }
})

declare module 'hooks/store' {
  interface StoreProvider {
    scan: ReturnType<typeof useScan>
  }
}
