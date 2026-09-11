import { reactive } from 'vue'
import { useToast } from 'hooks/toast'
import { api } from 'scripts/comfyAPI'

/**
 * Module-level state of the in-flight HuggingFace upload.
 *
 * BUG FIX: the upload state used to live inside `DialogHfUpload`, so closing
 * the dialog threw every piece of progress away - re-opening showed nothing
 * while the transfer kept running (or, before the backend fix, had silently
 * died with the HTTP request). The state now lives for the lifetime of the
 * page: the dialog binds to it, so re-opening it re-attaches to a running
 * upload and the progress bar is visible again.
 */
export const hfUploadState = reactive<{
  taskId: string | null
  active: boolean
  progress: number
  repoId: string
  pathInRepo: string
}>({
  taskId: null,
  active: false,
  progress: 0,
  repoId: '',
  pathInRepo: '',
})

const matches = (detail: { taskId?: string } | undefined) => {
  // Ignore events of a previous upload once a newer one has been started.
  return !hfUploadState.taskId || !detail?.taskId || detail.taskId === hfUploadState.taskId
}

/**
 * Websocket listeners are registered once, at module load, so progress and
 * completion events are handled even while the dialog is closed (they drive
 * the toasts and keep `hfUploadState` accurate for the next open).
 */
const { toast } = useToast()

api.addEventListener('update_hf_upload_progress', (event: CustomEvent) => {
  const detail = event.detail as { taskId?: string; progress?: number } | undefined
  if (!matches(detail)) return
  hfUploadState.active = true
  hfUploadState.progress = Math.floor(detail?.progress ?? 0)
})

api.addEventListener('hf_upload_complete', (event: CustomEvent) => {
  const detail = event.detail as
    { taskId?: string; repoId?: string; pathInRepo?: string } | undefined
  if (!matches(detail)) return
  hfUploadState.active = false
  hfUploadState.progress = 100
  hfUploadState.taskId = null
  toast.add({
    severity: 'success',
    summary: 'Success',
    detail: `${detail?.pathInRepo ?? hfUploadState.pathInRepo} -> ${detail?.repoId ?? hfUploadState.repoId}`,
    life: 5000,
  })
})

api.addEventListener('hf_upload_error', (event: CustomEvent) => {
  const detail = event.detail as { taskId?: string; error?: string } | undefined
  if (!matches(detail)) return
  hfUploadState.active = false
  hfUploadState.progress = 0
  hfUploadState.taskId = null
  toast.add({
    severity: 'error',
    summary: 'Error',
    detail: detail?.error ?? 'HuggingFace upload failed',
    life: 15000,
  })
})
