import { computed, reactive } from 'vue'
import { useI18nGlobal } from 'hooks/i18n'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { api } from 'scripts/comfyAPI'

/**
 * Module-level ZipNN task state.
 *
 * Mirrors `hooks/hfUpload`: the compression runs in the backend (cpu pool), so
 * the progress must survive closing the model window and must be re-attachable
 * when it is re-opened. `targetKey` ties a running task to the model it belongs
 * to so only that window shows the bar.
 */
export const zipnnState = reactive<{
  taskId: string | null
  active: boolean
  progress: number
  phase: string
  mode: 'compress' | 'decompress' | null
  targetKey: string | null
  /** The model a finished task belonged to (kept after `targetKey` clears). */
  lastTargetKey: string | null
}>({
  taskId: null,
  active: false,
  progress: 0,
  phase: 'prepare',
  mode: null,
  targetKey: null,
  lastTargetKey: null,
})

const { t } = useI18nGlobal()
const { toast } = useToast()

api.addEventListener('update_zipnn_progress', (event: CustomEvent) => {
  const detail = event.detail as
    | {
        taskId?: string
        progress?: number
        phase?: string
        mode?: 'compress' | 'decompress'
      }
    | undefined
  if (!detail || (zipnnState.taskId && detail.taskId !== zipnnState.taskId)) return
  zipnnState.active = true
  zipnnState.progress = Math.floor(detail.progress ?? 0)
  zipnnState.phase = detail.phase ?? 'tensors'
  if (detail.mode) zipnnState.mode = detail.mode
})

/**
 * A failed `pip install zipnn` carries the tail of pip's own output (compiler
 * errors, missing Python.h, ...). That is far too long for a toast, so the
 * first interesting line is shown and the rest is left to the console.
 */
const compactError = (raw: string): string => {
  const lines = raw
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
  if (lines.length <= 1) return raw
  const interesting =
    lines.find(line =>
      /fatal error|error:|No such file|not found|cannot|Could not|failed/i.test(line),
    ) ?? lines[lines.length - 1]
  const body = interesting.length > 220 ? `${interesting.slice(0, 217)}…` : interesting
  return `${body}\n${t('zipnnMoreInConsole', { n: lines.length - 1 })}`
}

/** Remembered so the "retry install" toast action can re-run the same job. */
let lastRequest: {
  mode: 'compress' | 'decompress'
  model: { type: string; pathIndex: number; fullname: string }
  modelKey: string
} | null = null

/**
 * What the most recently finished task did, consumed by the app-lifetime
 * watcher in `App.vue` that refreshes the grids and swaps an open model card
 * to the renamed file. Module-level state because the completion event fires
 * whether or not the dialog the task was started from is still mounted.
 */
export interface ZipnnSettle {
  ok: boolean
  /** Dialog-store key (`genModelKey`) of the model the task was started for. */
  targetKey: string | null
  type: string
  pathIndex: number
  subFolder: string
  /** File name (basename + extension) the model was renamed to, on success. */
  newFullname: string | null
}

let lastSettle: ZipnnSettle | null = null

/** Consume (once) the settle record of the most recently finished task. */
export const takeZipnnSettle = (): ZipnnSettle | null => {
  const settle = lastSettle
  lastSettle = null
  return settle
}

api.addEventListener('zipnn_complete', (event: CustomEvent) => {
  const detail = event.detail as
    | {
        taskId?: string
        ok?: boolean
        error?: string
        mode?: string
        fullname?: string
        installFailed?: boolean
        stats?: { originalBytes?: number; compressedBytes?: number }
      }
    | undefined
  if (!detail || (zipnnState.taskId && detail.taskId !== zipnnState.taskId)) return
  zipnnState.active = false
  zipnnState.progress = 100
  zipnnState.taskId = null
  zipnnState.lastTargetKey = zipnnState.targetKey
  zipnnState.targetKey = null

  // Record the outcome BEFORE any awaits elsewhere can consume it: the
  // `zipnnState.active` watcher in App.vue reads this right after this
  // handler flips `active` to false.
  const req = lastRequest
  const reqFullname = req?.model.fullname ?? ''
  const slash = reqFullname.lastIndexOf('/')
  lastSettle = req
    ? {
        ok: Boolean(detail.ok),
        targetKey: zipnnState.lastTargetKey,
        type: req.model.type,
        pathIndex: req.model.pathIndex,
        subFolder: slash >= 0 ? reqFullname.slice(0, slash) : '',
        newFullname: detail.ok ? (detail.fullname ?? null) : null,
      }
    : null

  if (!detail.ok) {
    const raw = detail.error ?? t('zipnnFailed')
    if (detail.installFailed) {
      // The backend caches a failed install for a few minutes, so the retry has
      // to ask for it explicitly (`force`).
      const retry = lastRequest
      toast.add({
        severity: 'error',
        summary: t('zipnnInstallFailed'),
        detail: compactError(raw),
        life: 20000,
        action: retry
          ? {
              label: t('zipnnRetryInstall'),
              onClick: () => {
                void startZipnn(retry.mode, retry.model, retry.modelKey, { force: true })
              },
            }
          : undefined,
      })
      return
    }
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: raw,
      life: 12000,
    })
    return
  }
  const stats = detail.stats ?? {}
  const ratio =
    stats.originalBytes && stats.compressedBytes
      ? ` (${Math.round((stats.compressedBytes / stats.originalBytes) * 100)}%)`
      : ''
  toast.add({
    severity: 'success',
    summary: (detail.mode === 'compress' ? t('zipnnCompressed') : t('zipnnDecompressed')) + ratio,
    life: 6000,
  })
})

export const zipnnAvailable = async (): Promise<boolean> => {
  try {
    const res = (await request('/zipnn/available')) as { available: boolean }
    return Boolean(res?.available)
  } catch {
    return false
  }
}

export const startZipnn = async (
  mode: 'compress' | 'decompress',
  model: { type: string; pathIndex: number; fullname: string },
  modelKey: string,
  options?: { force?: boolean },
): Promise<void> => {
  lastRequest = { mode, model, modelKey }
  zipnnState.taskId = null
  zipnnState.active = true
  zipnnState.progress = 0
  zipnnState.phase = 'prepare'
  zipnnState.mode = mode
  zipnnState.targetKey = modelKey
  try {
    const res = (await request(`/zipnn/${mode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options?.force ? { ...model, force: true } : model),
    })) as { taskId: string }
    zipnnState.taskId = res?.taskId ?? null
  } catch (error) {
    zipnnState.active = false
    zipnnState.taskId = null
    zipnnState.targetKey = null
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: error instanceof Error ? error.message : String(error),
      life: 12000,
    })
  }
}

/** True while a ZipNN task for this exact model is running. */
export const zipnnRunningFor = (modelKey: string | null) =>
  zipnnState.active && zipnnState.targetKey === modelKey

/**
 * Multi-select mode for the model grids ("Select files").
 *
 * Feature: a toolbar toggle reveals a round checkbox on every card/folder;
 * selecting one or more reveals bulk actions (add to workflow / delete).
 */
export const selectionState = reactive<{
  enabled: boolean
  selected: Record<string, boolean>
}>({
  enabled: false,
  selected: {},
})

export const useSelection = () => {
  const count = computed(() => Object.keys(selectionState.selected).length)

  const toggle = (key: string) => {
    if (selectionState.selected[key]) {
      delete selectionState.selected[key]
    } else {
      selectionState.selected[key] = true
    }
  }

  const clear = () => {
    selectionState.selected = {}
  }

  const enter = () => {
    selectionState.enabled = true
  }

  const exit = () => {
    selectionState.enabled = false
    clear()
  }

  return { count, toggle, clear, enter, exit, state: selectionState }
}
