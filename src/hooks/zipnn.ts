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

api.addEventListener('zipnn_complete', (event: CustomEvent) => {
  const detail = event.detail as
    | {
        taskId?: string
        ok?: boolean
        error?: string
        mode?: string
        stats?: { originalBytes?: number; compressedBytes?: number }
      }
    | undefined
  if (!detail || (zipnnState.taskId && detail.taskId !== zipnnState.taskId)) return
  zipnnState.active = false
  zipnnState.progress = 100
  zipnnState.taskId = null
  zipnnState.lastTargetKey = zipnnState.targetKey
  zipnnState.targetKey = null

  if (!detail.ok) {
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: detail.error ?? t('zipnnFailed'),
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
): Promise<void> => {
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
      body: JSON.stringify(model),
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
