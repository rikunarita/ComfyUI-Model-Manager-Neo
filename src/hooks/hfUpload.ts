import { reactive } from 'vue'
import { useI18nGlobal } from 'hooks/i18n'
import { useToast } from 'hooks/toast'
import { api } from 'scripts/comfyAPI'

/**
 * Upload phase reported by `py/upload_hf.py`.
 *
 * `prepare` covers the round trips before any byte moves (repository lookup,
 * pre-upload negotiation); `hash` is the local sha256 pass; `upload` is the
 * transfer itself. Surfacing the phase is what stops a multi-gigabyte upload
 * from looking frozen: the hashing pass alone can take minutes, and before
 * this the UI had nothing to show for it.
 */
type HfUploadPhase = 'prepare' | 'hash' | 'upload'

interface HfProgressDetail {
  taskId?: string
  uploadedSize?: number
  totalSize?: number
  progress?: number
  phase?: HfUploadPhase
  provider?: 'hf' | 'modelscope'
  /** False when the hub reports no per-chunk transfer progress (ModelScope). */
  chunked?: boolean
}

interface HfCompleteDetail {
  taskId?: string
  repoId?: string
  pathInRepo?: string
  skipped?: boolean
  deduplicated?: boolean
  transferredBytes?: number | null
  created?: boolean
  private?: boolean
  url?: string | null
  fileCount?: number
  skippedCount?: number
  provider?: 'hf' | 'modelscope'
}

/**
 * Module-level state of the in-flight Hugging Face upload.
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
  phase: HfUploadPhase
  repoId: string
  pathInRepo: string
  /** Hub provider of the running upload (toast wording / phase labels). */
  provider: 'hf' | 'modelscope'
  /** Whether the transfer reports per-chunk percentages (false: ModelScope,
   *  whose hub library consumes the payload opaquely - the bar renders
   *  indeterminate during its transfer phase instead of a frozen number). */
  chunked: boolean
}>({
  taskId: null,
  active: false,
  progress: 0,
  phase: 'prepare',
  repoId: '',
  pathInRepo: '',
  provider: 'hf',
  chunked: true,
})

/**
 * Task ids whose completion already arrived.
 *
 * `POST /hf/upload` answers as soon as the background task is queued, but a
 * fast upload (a duplicate short-circuit, or a Hub-side dedup that moves no
 * bytes) can finish before the browser has read that response. Without this
 * guard `handleUpload` would then write a task id back into the state *after*
 * the completion had already cleared it, leaving a stale id that filters the
 * events of the next upload.
 */
const finishedTaskIds = new Set<string>()

const rememberFinished = (taskId?: string) => {
  if (!taskId) return
  finishedTaskIds.add(taskId)
  while (finishedTaskIds.size > 8) {
    const oldest = finishedTaskIds.values().next().value
    if (oldest === undefined) break
    finishedTaskIds.delete(oldest)
  }
}

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
const { t } = useI18nGlobal()

api.addEventListener('update_hf_upload_progress', (event: CustomEvent) => {
  const detail = event.detail as HfProgressDetail | undefined
  if (!matches(detail)) return
  if (detail?.provider) hfUploadState.provider = detail.provider
  if (detail?.chunked !== undefined) hfUploadState.chunked = detail.chunked
  hfUploadState.active = true
  hfUploadState.progress = Math.floor(detail?.progress ?? 0)
  hfUploadState.phase = detail?.phase ?? 'upload'
})

const nsOf = (provider?: 'hf' | 'modelscope') =>
  provider === 'modelscope' ? 'msUpload' : 'hfUpload'

const reportHfSkipped = (ns: string, repoId: string, url: string) => {
  // huggingface_hub skips empty commits: the identical file already sits at
  // the destination. Reporting that as a plain success is what made a
  // re-upload look like a silently broken upload.
  toast.add({
    severity: 'warn',
    summary: t(`${ns}.skipped`),
    detail: t(`${ns}.skippedDetail`, { repo: repoId }) + url + t(`${ns}.skippedHint`),
    life: 15000,
  })
}

const reportHfDeduplicated = (ns: string, repoId: string, pathInRepo: string, url: string) => {
  // The commit really happened, but Hugging Face's object store already held
  // the identical bytes ("Upload 0 LFS files"), so not one byte travelled.
  // A bare "Success" next to a bar that never moved reads as a broken
  // upload; say what actually happened and link the committed file.
  toast.add({
    severity: 'info',
    summary: t(`${ns}.deduplicated`),
    detail: t(`${ns}.deduplicatedDetail`, { path: pathInRepo, repo: repoId }) + url,
    life: 15000,
  })
}

const reportHfSuccess = (
  ns: string,
  repoId: string,
  pathInRepo: string,
  created: boolean,
  priv: boolean,
  fileCount = 1,
) => {
  const createdNote = created
    ? t(priv ? `${ns}.createdPrivate` : `${ns}.createdPublic`, { repo: repoId })
    : ''
  toast.add({
    severity: 'success',
    summary: fileCount > 1 ? t(`${ns}.successMany`, { n: fileCount }) : t(`${ns}.success`),
    detail: `${pathInRepo} -> ${repoId}${createdNote ? ` (${createdNote})` : ''}`,
    life: 5000,
  })
}

api.addEventListener('hf_upload_complete', (event: CustomEvent) => {
  const detail = (event.detail ?? {}) as HfCompleteDetail
  if (!matches(detail)) return
  rememberFinished(detail.taskId)
  hfUploadState.active = false
  hfUploadState.progress = 100
  hfUploadState.phase = 'upload'
  hfUploadState.taskId = null

  const repoId = detail.repoId || hfUploadState.repoId
  const pathInRepo = detail.pathInRepo || hfUploadState.pathInRepo
  const url = detail.url ? `: ${detail.url}` : ''

  const ns = nsOf(detail.provider)
  if (detail.skipped) reportHfSkipped(ns, repoId, url)
  else if (detail.deduplicated) reportHfDeduplicated(ns, repoId, pathInRepo, url)
  else
    reportHfSuccess(
      ns,
      repoId,
      pathInRepo,
      Boolean(detail.created),
      Boolean(detail.private),
      detail.fileCount ?? 1,
    )
})

api.addEventListener('hf_upload_error', (event: CustomEvent) => {
  const detail = event.detail as { taskId?: string; error?: string } | undefined
  if (!matches(detail)) return
  rememberFinished(detail?.taskId)
  hfUploadState.active = false
  hfUploadState.progress = 0
  hfUploadState.phase = 'prepare'
  hfUploadState.taskId = null
  toast.add({
    severity: 'error',
    summary: t('hfUpload.error'),
    detail: detail?.error ?? t('hfUpload.errorFallback'),
    life: 15000,
  })
})

/** Called by the dialog right before it starts a new upload. */
export const resetHfUploadState = () => {
  hfUploadState.taskId = null
  hfUploadState.active = true
  hfUploadState.progress = 0
  hfUploadState.phase = 'prepare'
  // NOTE: `provider` is NOT reset here - the upload wizard owns the platform
  // selection and the backend events carry the provider of the running task.
  hfUploadState.chunked = true
}

/** Whether a task id has already been reported as finished. */
export const isFinishedTask = (taskId?: string | null) => !!taskId && finishedTaskIds.has(taskId)
