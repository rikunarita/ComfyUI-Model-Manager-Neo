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
  mode: ZipnnMode | null
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
const { toast, confirm } = useToast()

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
  mode: ZipnnMode
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
  /** What the task operated on: single model, folder batch, or delta pair. */
  kind: 'model' | 'folder' | 'delta'
}

let lastSettle: ZipnnSettle | null = null

/** Consume (once) the settle record of the most recently finished task. */
export const takeZipnnSettle = (): ZipnnSettle | null => {
  const settle = lastSettle
  lastSettle = null
  return settle
}

interface ZipnnCompleteDetail {
  taskId?: string
  ok?: boolean
  error?: string
  mode?: string
  fullname?: string
  kind?: string
  installFailed?: boolean
  stats?: { originalBytes?: number; compressedBytes?: number }
}

/** Flip the progress state to "just finished" (kept for the next open). */
const settleZipnnState = () => {
  zipnnState.active = false
  zipnnState.progress = 100
  zipnnState.taskId = null
  zipnnState.lastTargetKey = zipnnState.targetKey
  zipnnState.targetKey = null
}

/**
 * Record the outcome BEFORE any awaits elsewhere can consume it: the
 * app-lifetime settle watcher reads this right after the handler flips
 * `active` to false.
 */
const recordZipnnSettle = (detail: ZipnnCompleteDetail) => {
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
        kind: detail.kind === 'folder' || detail.kind === 'delta' ? detail.kind : 'model',
      }
    : null
}

/**
 * Sequential folder-batch queue: start the next folder once this one
 * succeeded; a failure aborts the rest of the queue.
 */
const advanceZipnnQueue = (ok: boolean) => {
  if (!ok) {
    batchQueue.length = 0
    return
  }
  const next = batchQueue.shift()
  if (next) void startZipnnBatch(next.mode, next.folder, next.key)
}

const reportZipnnFailure = (detail: ZipnnCompleteDetail) => {
  const raw = detail.error ?? t('zipnnFailed')
  if (!detail.installFailed) {
    toast.add({ severity: 'error', summary: t('error'), detail: raw, life: 12000 })
    return
  }
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
            void startZipnn(
              retry.mode === 'auto' ? 'compress' : retry.mode,
              retry.model,
              retry.modelKey,
              { force: true },
            )
          },
        }
      : undefined,
  })
}

const reportZipnnSuccess = (detail: ZipnnCompleteDetail) => {
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
}

api.addEventListener('zipnn_complete', (event: CustomEvent) => {
  const detail = event.detail as ZipnnCompleteDetail | undefined
  if (!detail || (zipnnState.taskId && detail.taskId !== zipnnState.taskId)) return
  settleZipnnState()
  recordZipnnSettle(detail)
  advanceZipnnQueue(Boolean(detail.ok))
  // App-level listener refreshes the grids / swaps an open card for every
  // settled task. (A watcher on `active` would miss queued batches, which
  // keep it true across tasks.)
  window.dispatchEvent(new CustomEvent('mm-zipnn-settled'))
  if (detail.ok) reportZipnnSuccess(detail)
  else reportZipnnFailure(detail)
})

/**
 * Shared task bootstrap for the four starters below: remember the request
 * (retry-install toast), reset the module-level progress state onto the new
 * target, POST to the endpoint and report a failed start as a toast.
 */
const beginTask = async (
  mode: ZipnnMode,
  model: { type: string; pathIndex: number; fullname: string },
  modelKey: string,
  endpoint: string,
  payload: unknown,
): Promise<void> => {
  lastRequest = { mode, model, modelKey }
  zipnnState.taskId = null
  zipnnState.active = true
  zipnnState.progress = 0
  zipnnState.phase = 'prepare'
  zipnnState.mode = mode
  zipnnState.targetKey = modelKey
  try {
    const res = (await request(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
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

/**
 * The single-model compress/decompress confirmation, shared by the card
 * corner button and the model-detail action row (they rendered byte
 * identical confirm blocks before).
 */
export const confirmSingleZipnn = (
  model: {
    type: string
    pathIndex: number
    subFolder: string
    basename: string
    extension: string
  },
  modelKey: string,
): void => {
  const compressing = !model.basename.endsWith('.znn')
  confirm.require({
    message: compressing ? t('zipnnConfirmCompress') : t('zipnnConfirmDecompress'),
    header: compressing ? t('zipnnCompress') : t('zipnnDecompress'),
    icon: 'pi pi-info-circle',
    rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
    acceptProps: { label: compressing ? t('zipnnCompress') : t('zipnnDecompress') },
    accept: () => {
      void startZipnn(
        compressing ? 'compress' : 'decompress',
        {
          type: model.type,
          pathIndex: model.pathIndex,
          fullname: [model.subFolder, `${model.basename}${model.extension}`]
            .filter(Boolean)
            .join('/'),
        },
        modelKey,
      )
    },
    reject: () => {},
  })
}

const startZipnn = async (
  mode: 'compress' | 'decompress',
  model: { type: string; pathIndex: number; fullname: string },
  modelKey: string,
  options?: { force?: boolean },
): Promise<void> => {
  await beginTask(
    mode,
    model,
    modelKey,
    `/zipnn/${mode}`,
    options?.force ? { ...model, force: true } : model,
  )
}

/** True while a ZipNN task for this exact model is running. */
export const zipnnRunningFor = (modelKey: string | null) =>
  zipnnState.active && zipnnState.targetKey === modelKey

/**
 * Folder-batch queue: several folders can be selected at once, but the
 * progress state tracks a single task, so batches run one after another.
 * The completion handler starts the next entry (and drops the queue on
 * failure).
 */
/** Direction of a ZipNN task; `auto` is resolved by the backend. */
export type ZipnnMode = 'compress' | 'decompress' | 'auto'

export interface ZipnnBatchItem {
  /** `auto` lets the backend pick the direction from the folder content. */
  mode: ZipnnMode
  folder: { type: string; pathIndex: number; folder: string }
  key: string
}

const batchQueue: ZipnnBatchItem[] = []

export const queueZipnnBatches = (items: ZipnnBatchItem[]) => {
  batchQueue.push(...items)
  const next = batchQueue.shift()
  if (next) void startZipnnBatch(next.mode, next.folder, next.key)
}

/**
 * Batch-compress / batch-decompress a whole folder (selection bar button and
 * the folder-card corner button). On the backend every compressed file moves
 * into the bundle folder `X_DeltaZNN` (and back out on decompress); delta
 * folders batch-restore their fine-tuned models.
 */
export const startZipnnBatch = async (
  mode: ZipnnMode,
  folder: { type: string; pathIndex: number; folder: string },
  folderKey: string,
): Promise<void> => {
  // Client-side guard: never send an incomplete payload (the backend rejects
  // it with "mode, type and folder are required"). The detail string carries
  // the offending values so any recurrence is diagnosable from the toast.
  if (!folder || !folder.type || !folder.folder) {
    const got = `type=${folder?.type ?? '-'}, pathIndex=${folder?.pathIndex ?? '-'}, folder=${folder?.folder ?? '-'}`
    console.warn('[Model Manager Neo] batch target unresolved:', got)
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: `${t('zipnnBatchInvalidTarget')} [${got}]`,
      life: 12000,
    })
    return
  }
  await beginTask(
    mode,
    { type: folder.type, pathIndex: folder.pathIndex, fullname: folder.folder },
    folderKey,
    `/zipnn/batch-folder`,
    { mode, ...folder },
  )
}

/** Delta-compress a fine-tuned model against its base (selection bar). */
export const startZipnnDelta = async (
  base: { type: string; pathIndex: number; fullname: string },
  ft: { type: string; pathIndex: number; fullname: string },
  ftKey: string,
): Promise<void> => {
  await beginTask('compress', ft, ftKey, `/zipnn/delta-compress`, {
    type: ft.type,
    pathIndex: ft.pathIndex,
    fullname: ft.fullname,
    baseFullname: base.fullname,
  })
}

/** Restore a fine-tuned model from its delta file (needs the base model). */
export const startZipnnDeltaDecompress = async (
  model: { type: string; pathIndex: number; fullname: string },
  modelKey: string,
): Promise<void> => {
  await beginTask('decompress', model, modelKey, `/zipnn/delta-decompress`, model)
}

/**
 * Multi-select mode for the model grids ("Select files").
 *
 * Feature: a toolbar toggle reveals a round checkbox on every card/folder;
 * selecting one or more reveals bulk actions (add to workflow / delete /
 * ZipNN batch / star).
 *
 * `kinds` records what each selected key is so the ZipNN bundle rule can be
 * enforced: a bundle folder (`*_DeltaZNN` / legacy `*_ZNN`) and a plain
 * folder can never be selected at the same time (adding one drops the
 * bundle side with a warning).
 */
type SelectionKind = 'model' | 'folder' | 'znn-folder'

const selectionState = reactive<{
  enabled: boolean
  selected: Record<string, boolean>
  kinds: Record<string, SelectionKind>
}>({
  enabled: false,
  selected: {},
  kinds: {},
})

export const useSelection = () => {
  const count = computed(() => Object.keys(selectionState.selected).length)

  const selectedKeysOfKind = (kind: SelectionKind) =>
    Object.keys(selectionState.selected).filter(key => selectionState.kinds[key] === kind)

  const toggle = (key: string, kind: SelectionKind = 'model') => {
    if (selectionState.selected[key]) {
      delete selectionState.selected[key]
      delete selectionState.kinds[key]
      return
    }
    if (kind === 'znn-folder' && selectedKeysOfKind('folder').length > 0) {
      // Mixing is refused: the already-selected plain folders stay, the
      // `*_ZNN` folder never joins them.
      toast.add({ severity: 'warn', summary: t('selectionZnnMixed'), life: 6000 })
      return
    }
    if (kind === 'folder' && selectedKeysOfKind('znn-folder').length > 0) {
      // Drop the already-selected `*_ZNN` folders and warn.
      for (const znnKey of selectedKeysOfKind('znn-folder')) {
        delete selectionState.selected[znnKey]
        delete selectionState.kinds[znnKey]
      }
      toast.add({ severity: 'warn', summary: t('selectionZnnMixed'), life: 6000 })
    }
    selectionState.selected[key] = true
    selectionState.kinds[key] = kind
  }

  const clear = () => {
    selectionState.selected = {}
    selectionState.kinds = {}
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
