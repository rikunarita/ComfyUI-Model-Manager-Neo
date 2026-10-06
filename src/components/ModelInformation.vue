<template>
  <div class="flex flex-col gap-4">
    <!--
      Information table: the parsed YAML front-matter of the model notes
      (author, base model, hashes, format/precision, platform, model page,
      every preview URL, unknown keys verbatim at the end). Read-only by
      default; the edit mode (warning-gated) rewrites the front-matter block
      of the notes when the form is saved.
    -->
    <div v-if="!editing" class="flex justify-end">
      <Button
        v-if="editable"
        variant="ghost"
        size="icon-sm"
        :title="$t('informationEdit')"
        :aria-label="$t('informationEdit')"
        @click="requestEdit"
      >
        <Pencil class="size-4" />
      </Button>
    </div>

    <!--
      Same scroll + per-row sticky copy treatment as the base-info table:
      each row ends with a sticky copy cell pinned to the visible right edge
      while the table scrolls sideways.
    -->
    <ResponseScroll v-if="rows.length && !editing" class="overflow-x-auto">
      <table class="w-full border-collapse border border-mm-border">
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="group h-8 border-b border-mm-border">
            <td
              class="w-40 border-r border-mm-border bg-mm-fg/6 px-4 text-mm-muted-fg backdrop-blur-sm"
            >
              {{ labelOf(row) }}
            </td>
            <td class="px-4 break-all text-mm-fg">
              <InformationValue :row="row" />
            </td>
            <!-- Sticky copy cell: visible-range right edge, per row. -->
            <td class="sticky right-0 w-8 min-w-8 px-1 group-hover:bg-mm-bg/85">
              <CopyRowButton :text="rowText(row)" />
            </td>
          </tr>
        </tbody>
      </table>
    </ResponseScroll>

    <!-- Edit mode: scalar fields become inputs; the preview list a textarea. -->
    <div v-if="editing && draft" class="flex flex-col gap-3">
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2 text-mm-muted-fg">
          <Info class="size-4 shrink-0" />
          <span class="text-sm">{{ $t('informationEditHint') }}</span>
        </div>
        <div class="flex gap-2">
          <Button variant="secondary" size="sm" @click="editing = false">
            {{ $t('cancel') }}
          </Button>
          <Button size="sm" @click="applyDraft">
            {{ $t('save') }}
          </Button>
        </div>
      </div>

      <div class="grid grid-cols-[10rem_1fr] gap-2">
        <template v-for="key in scalarKeys" :key="key">
          <label class="flex items-center text-sm text-mm-muted-fg">{{ labelFor(key) }}</label>
          <Input
            :model-value="String(draft[key] ?? '')"
            class="h-8"
            @update:model-value="draft[key] = $event"
          />
        </template>

        <template v-if="isObj(draft.hashes)">
          <template v-for="(value, key) in draft.hashes" :key="`h-${key}`">
            <label class="flex items-center pl-4 text-sm text-mm-muted-fg">{{ key }}</label>
            <Input
              :model-value="String(draft.hashes[key] ?? '')"
              class="h-8"
              @update:model-value="draft.hashes[key] = $event"
            />
          </template>
        </template>

        <template v-if="isObj(draft.metadata)">
          <template v-for="(value, key) in draft.metadata" :key="`m-${key}`">
            <template v-if="!HIDDEN_METADATA_KEYS.includes(String(key))">
              <label class="flex items-center pl-4 text-sm text-mm-muted-fg">
                {{ labelForMeta(String(key)) }}
              </label>
              <Input
                :model-value="String(draft.metadata[key] ?? '')"
                class="h-8"
                @update:model-value="draft.metadata[key] = $event"
              />
            </template>
          </template>
        </template>

        <template v-for="key in previewKeyList" :key="key">
          <label class="text-sm text-mm-muted-fg">{{ labelFor(key) }}</label>
          <textarea
            :value="previewText"
            class="min-h-24 w-full rounded-mm-ctl border border-mm-border bg-mm-fg/4 px-3 py-2 text-sm text-mm-fg outline-none focus:border-mm-accent"
            rows="4"
            @input="setPreviewText(($event.target as HTMLTextAreaElement).value)"
          ></textarea>
        </template>

        <template v-for="key in unknownKeys" :key="key">
          <label class="flex items-center text-sm text-mm-muted-fg">{{ key }}</label>
          <Input
            v-if="isScalar(draft[key])"
            :model-value="String(draft[key] ?? '')"
            class="h-8"
            @update:model-value="draft[key] = $event"
          />
          <code v-else class="text-xs break-all text-mm-muted-fg">
            {{ JSON.stringify(draft[key]) }}
          </code>
        </template>
      </div>
    </div>

    <!--
      ZipNN compression breakdown: the dtype mix recorded in
      `znn_compressed_vectors` plus the Neo-extension badge. The badge says
      what interoperability the file has: Neo-extended files stay lossless
      inside Neo but official ZipNN tools refuse their blobs.
    -->
    <div v-if="znnInfo && !editing" class="flex flex-col gap-2">
      <div class="text-sm font-medium text-mm-muted-fg">{{ $t('info.znnCompression') }}</div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="font-mono text-xs break-all text-mm-fg">{{ znnInfo.summary }}</span>
        <Tooltip v-if="znnInfo.extended" :delay-duration="200">
          <TooltipTrigger as-child>
            <span
              class="rounded-full border border-mm-warning/40 bg-mm-warning/15 px-2 py-0.5 text-xs font-medium text-mm-warning"
            >
              {{ $t('info.znnExtended') }}
            </span>
          </TooltipTrigger>
          <TooltipContent side="bottom" class="max-w-sm">
            {{ $t('info.znnExtendedTooltip') }}
          </TooltipContent>
        </Tooltip>
      </div>
    </div>

    <!--
      The raw file metadata (safetensors `__metadata__`) keeps its own table
      below the parsed information, keys verbatim. It is skipped for download
      search results, whose `metadata` is the Civitai file metadata the parsed
      table already renders.
    -->
    <div v-if="rawRows.length" class="flex flex-col gap-2">
      <div class="text-sm font-medium text-mm-muted-fg">{{ $t('info.fileMetadata') }}</div>
      <table class="w-full border-collapse border border-mm-border">
        <tbody>
          <tr v-for="row in rawRows" :key="row.key" class="h-8 border-b border-mm-border">
            <td
              class="w-40 border-r border-mm-border bg-mm-fg/6 px-4 text-mm-muted-fg backdrop-blur-sm"
            >
              {{ row.key }}
            </td>
            <td class="px-4 break-all text-mm-fg">{{ row.value }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!--
      Tensor structure of the safetensors header. Only local safetensors
      models carry it; see the tree comment below for the rendering.
    -->
    <div v-if="tensors.length && !editing" class="flex flex-col gap-2">
      <div class="flex items-baseline justify-between gap-2">
        <div class="text-sm font-medium text-mm-muted-fg">{{ $t('info.tensors') }}</div>
        <div class="text-xs text-mm-muted-fg">{{ tensorsSummary }}</div>
      </div>
      <!--
        TENSOR TREE: safetensors tensor names are dotted paths
        (`model.layers.0.self_attn.q_proj.weight`), so the flat 500-row table
        is now a folder tree - one node per dot segment, HF-viewer style.
        Folder rows carry a folder icon that collapses / expands the node
        (closed `Folder`, open `FolderOpen`) plus the aggregate tensor and
        parameter count; leaf rows keep the exact name tail / dtype / shape.
        Everything starts MAXIMALLY COLLAPSED (only the top level is shown)
        and very large nodes page their leaves with an explicit show-all.
      -->
      <div class="overflow-hidden rounded-mm-ctl border border-mm-border">
        <table class="w-full border-collapse font-mono text-xs">
          <thead>
            <tr
              class="border-b border-mm-border bg-mm-fg/6 text-left text-mm-muted-fg backdrop-blur-sm"
            >
              <th class="px-4 py-2 font-medium">{{ $t('info.tensorName') }}</th>
              <th class="w-24 px-4 py-2 font-medium">{{ $t('info.tensorDtype') }}</th>
              <th class="w-44 px-4 py-2 font-medium">{{ $t('info.tensorShape') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in tensorRows" :key="row.key">
              <tr
                v-if="row.kind === 'folder'"
                class="h-7 cursor-pointer border-b border-mm-border select-none hover:bg-mm-fg/6"
                :title="row.path"
                @click="toggleTensorNode(row.path)"
              >
                <td class="px-2" :style="{ paddingLeft: `${8 + row.depth * 16}px` }" colspan="3">
                  <span class="flex items-center gap-1.5">
                    <component
                      :is="expandedNodes.has(row.path) ? FolderOpen : Folder"
                      class="size-3.5 shrink-0 text-mm-muted-fg"
                    />
                    <span class="font-medium text-mm-fg">{{ row.segment }}</span>
                    <span class="text-mm-muted-fg">
                      {{
                        $t('info.tensorsCount', {
                          count: row.totalCount ?? 0,
                          params: compactCount(row.totalParams ?? 0),
                        })
                      }}
                    </span>
                  </span>
                </td>
              </tr>
              <tr v-else-if="row.kind === 'leaf'" class="h-7 border-b border-mm-border">
                <td
                  class="px-2 break-all text-mm-fg"
                  :style="{ paddingLeft: `${26 + row.depth * 16}px` }"
                >
                  {{ row.segment }}
                </td>
                <td class="px-4 text-mm-muted-fg">{{ row.tensor?.dtype }}</td>
                <td class="px-4 text-mm-muted-fg">{{ formatShape(row.tensor?.shape ?? []) }}</td>
              </tr>
              <tr v-else class="h-7 border-b border-mm-border">
                <td :style="{ paddingLeft: `${26 + row.depth * 16}px` }" colspan="3">
                  <Button
                    variant="ghost"
                    size="xs"
                    class="border-0 bg-transparent shadow-none backdrop-blur-none"
                    @click="toggleTensorLeaves(row.path)"
                  >
                    {{
                      row.allLeaves
                        ? $t('info.tensorsShowLess')
                        : $t('info.tensorsShowAll', { count: row.totalCount })
                    }}
                  </Button>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <div
      v-if="!rows.length && !rawRows.length && !tensors.length && !editing"
      class="flex flex-col items-center gap-2 py-5"
    >
      <!-- BUG FIX: `pi pi-info-circle` rendered empty (PrimeIcons removed). -->
      <Info class="size-5 text-mm-muted-fg" />
      <div class="text-sm text-mm-muted-fg">{{ $t('noMetadata') }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Folder, FolderOpen, Info, Pencil } from '@lucide/vue'
import { computed, ref, toRaw } from 'vue'
import { useI18n } from 'vue-i18n'
import CopyRowButton from 'components/CopyRowButton.vue'
import InformationValue from 'components/InformationValue.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Input } from 'components/ui/input'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { useModelDescription, useModelMetadata } from 'hooks/model'
import { useToast } from 'hooks/toast'
import { type BaseModel, type SafetensorsTensor } from 'types/typings'
import { compareText } from 'utils/modelFilter'
import {
  type InformationRow,
  buildInformationRows,
  parseFrontmatter,
  writeFrontmatter,
} from 'utils/modelInformation'
import { PERF_PREFIX, perfTime } from 'utils/perf'
import {
  buildTensorTreePayload,
  createTensorTreeIndex,
  tensorParams,
  tensorTail,
} from 'utils/tensorTree'

interface Props {
  /** The detail window's edit mode gates the (warning-gated) metadata edit. */
  editable?: boolean
}
defineProps<Props>()

const { t, te } = useI18n()
const { confirm } = useToast()
const { metadata, model } = useModelMetadata()
const { description } = useModelDescription()

const rows = computed<InformationRow[]>(() => buildInformationRows(description.value))

/** Plain-text form of a row value, for the hover-revealed copy button. */
const rowText = (row: InformationRow) =>
  row.kind === 'links' ? (row.values ?? []).join('\n') : String(row.value ?? '')

/** Localised labels win; verbatim keys render as-is. */
const labelOf = (row: InformationRow) => {
  if (row.labelKey && te(row.labelKey)) return t(row.labelKey)
  return row.labelRaw ?? row.labelKey ?? ''
}

const stringify = (value: unknown): string => {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

/* ---- ZipNN compression breakdown ---------------------------------------- */

/**
 * The ZipNN/Neo bookkeeping keys of `__metadata__`. They get a dedicated
 * rendering (the dtype breakdown row + the Neo-extension badge below, and
 * the size breakdown rows of the base-info table) instead of the raw
 * key/value dump - `znn_compressed_vectors` alone is a multi-kilobyte JSON
 * string on MoE files.
 */
const ZNN_META_KEYS = /^znn_(compressed_vectors|neo_)/

/**
 * Compression summary of a `.znn.safetensors` model: the per-dtype tensor
 * counts recorded in `znn_compressed_vectors` (`bfloat16×412, uint8×3`) and
 * whether the file is Neo-extended (`znn_neo_extended="1"` - official ZipNN
 * tools refuse its blobs with an explicit error, so the badge matters).
 */
const znnInfo = computed<{ summary: string; extended: boolean } | null>(() => {
  const source = metadata.value
  if (!source || (model.value as any).downloadPlatform) return null
  const infosRaw = source['znn_compressed_vectors']
  if (typeof infosRaw !== 'string' || !infosRaw) return null
  let counts = new Map<string, number>()
  try {
    const infos = JSON.parse(infosRaw) as unknown
    // the record form {name: {dtype, shape}} — anything else (array,
    // scalar, null) is a corrupt/hostile value: hide the section instead
    // of rendering nonsense counts
    if (!infos || typeof infos !== 'object' || Array.isArray(infos)) return null
    for (const spec of Object.values(infos as Record<string, { dtype?: unknown }>)) {
      const dtype = String(spec?.dtype ?? '?')
      counts.set(dtype, (counts.get(dtype) ?? 0) + 1)
    }
  } catch {
    return null
  }
  if (!counts.size) return null
  const summary = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || compareText(a[0], b[0]))
    .map(([dtype, count]) => `${dtype}\u00d7${count}`)
    .join(', ')
  return { summary, extended: source['znn_neo_extended'] === '1' }
})

/**
 * Raw file metadata (safetensors `__metadata__`). Download search results
 * carry the Civitai *file* metadata here, which the parsed table above
 * already renders - showing it twice (including the `isRequired` / `size`
 * keys the table deliberately omits) would only be noise. The ZipNN/Neo
 * bookkeeping keys are rendered by the dedicated section instead.
 */
const rawRows = computed(() => {
  const source = metadata.value
  if (!source || (model.value as any).downloadPlatform) return []
  const entries = Object.entries(source).filter(([key]) => !ZNN_META_KEYS.test(key))
  if (!entries.length) return []
  return entries.map(([key, value]) => ({ key, value: stringify(value) }))
})

/* ---- tensor tree (safetensors header) ----------------------------------- */

/** Leaves rendered per node before the explicit "show all" expansion. */
const TENSOR_PAGE = 500

/**
 * The form model WITHOUT Vue's reactive wrapper.
 *
 * `tensors` and `tensorTree` are large read-only payloads that
 * `ModelContent.vue` shares by reference into the form data, which is a deep
 * `ref` - so reading them through `model.value` hands out Proxy-wrapped arrays
 * whose every element access goes through a trap. Walking 65k tensors (and
 * validating an 87k-node tree) that way costs more than the fold it replaced.
 * `toRaw` keeps the ref-level dependency (a replaced form still re-runs this)
 * while giving the decoder plain arrays. Nothing here writes to the model.
 */
const rawModel = () => toRaw(model.value) as BaseModel

const tensors = computed<SafetensorsTensor[]>(() => {
  const list = rawModel().tensors
  return Array.isArray(list) ? list : []
})

/** One rendered row of the tensor table (folder / leaf / "show all"). */
interface TensorRow {
  key: string
  kind: 'folder' | 'leaf' | 'more'
  depth: number
  path: string
  segment: string
  tensor?: SafetensorsTensor
  totalCount?: number
  totalParams?: number
  allLeaves?: boolean
}

/**
 * Random access over the tensor tree (Phase 6).
 *
 * The backend folds the tree in Rust while it parses the header anyway and
 * ships the compact pre-order table; `createTensorTreeIndex` validates it and
 * answers children/leaves queries WITHOUT materialising the ~87k node objects a
 * big MoE header used to cost (measured 1,190 ms of main-thread JS per dialog
 * open on the 2 vCPU dev container -> 13 ms; BENCH §11.3). A response that
 * carries no tree (a non-safetensors model, a tree dropped by the backend's
 * file-changed guard, or an unavailable native core) falls back to the same
 * fold in JS, so there is exactly ONE rendering path.
 */
const tensorIndex = computed(() => {
  const list = tensors.value
  const payload = rawModel().tensorTree
  // C5: the two sources get their own sample names, so `__mmNeoPerf.summary()`
  // shows whether the Rust payload path or the JS fallback ran (and what each
  // cost) instead of one blended number.
  if (payload) {
    const fromBackend = perfTime(`${PERF_PREFIX}info.tensorTree.decode`, () =>
      createTensorTreeIndex(payload, list),
    )
    if (fromBackend) return fromBackend
    // A payload this decoder does not trust (wrong version, inconsistent
    // counts, a leaf index outside the tensor list): fall through to the JS
    // fold rather than render a wrong table.
  }
  return perfTime(`${PERF_PREFIX}info.tensorTree.fallbackFold`, () =>
    createTensorTreeIndex(buildTensorTreePayload(list), list),
  )
})

/** Expanded folder paths; empty by default = maximally collapsed. */
const expandedNodes = ref<Set<string>>(new Set())
/** Per-node leaf page size override (show-all toggle). */
const allLeavesNodes = ref<Set<string>>(new Set())

const toggleTensorNode = (path: string) => {
  const next = new Set(expandedNodes.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  expandedNodes.value = next
}

const toggleTensorLeaves = (path: string) => {
  const next = new Set(allLeavesNodes.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  allLeavesNodes.value = next
}

/** Depth-first row list honouring the collapsed/expanded + paging state.
 *  Only the EXPANDED part of the tree is touched: a collapsed MoE renders its
 *  root child, not its 87k nodes. */
const tensorRows = computed<TensorRow[]>(() =>
  perfTime(`${PERF_PREFIX}info.tensorRows`, () => {
    const index = tensorIndex.value
    const rows: TensorRow[] = []
    if (!index) return rows
    const walk = (nodeIndex: number, path: string, depth: number) => {
      for (const childIndex of index.childrenOf(nodeIndex)) {
        const childPath = index.pathOf(childIndex, path)
        const view = index.viewOf(childIndex, path)
        rows.push({
          key: `f:${childPath}`,
          kind: 'folder',
          depth,
          path: childPath,
          segment: view.segment,
          totalCount: view.totalCount,
          totalParams: view.totalParams,
        })
        if (expandedNodes.value.has(childPath)) walk(childIndex, childPath, depth + 1)
      }
      const all = allLeavesNodes.value.has(path)
      const leaves = index.tensorsOf(nodeIndex, path)
      const shown = all ? leaves : leaves.slice(0, TENSOR_PAGE)
      for (const tensor of shown) {
        const tail = tensorTail(path, tensor)
        rows.push({
          key: `t:${tensor.name}`,
          kind: 'leaf',
          depth,
          path: tensor.name,
          segment: tail || tensor.name,
          tensor,
        })
      }
      if (leaves.length > TENSOR_PAGE) {
        rows.push({
          key: `m:${path}`,
          kind: 'more',
          depth,
          path,
          segment: '',
          totalCount: leaves.length,
          allLeaves: all,
        })
      }
    }
    walk(0, '', 0)
    return rows
  }),
)

/** Structural shape rendering, e.g. `[1280, 4, 2]`; scalars read `[]`. */
const formatShape = (shape: number[]) => `[${(shape ?? []).join(', ')}]`

const compactCount = (value: number): string => {
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`
  return String(value)
}

const tensorsSummary = computed(() => {
  const index = tensorIndex.value
  // The root's subtree aggregates ARE the whole-file totals (every tensor is a
  // leaf of exactly one node), so the summary is O(1) instead of a reduce over
  // every tensor.
  const count = index ? index.rootCount : tensors.value.length
  const params = index
    ? index.rootParams
    : tensors.value.reduce((total, tensor) => total + tensorParams(tensor), 0)
  return t('info.tensorsSummary', {
    count,
    params: compactCount(params),
  })
})

/* ---- edit mode --------------------------------------------------------- */

const HIDDEN_METADATA_KEYS = ['isRequired', 'size']
const KNOWN_KEYS = ['author', 'baseModel', 'hashes', 'metadata', 'modelPage', 'preview', 'website']
const LABELLED: Record<string, string> = {
  author: 'info.author',
  baseModel: 'info.baseModel',
  website: 'info.website',
  modelPage: 'info.modelPage',
  preview: 'info.preview',
}

const editing = ref(false)
const draft = ref<Record<string, any> | null>(null)

const isObj = (value: unknown) =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const labelForMeta = (key: string) => (key === 'format' || key === 'fp' ? t(`info.${key}`) : key)

const isScalar = (value: unknown) =>
  value == null ||
  typeof value === 'string' ||
  typeof value === 'number' ||
  typeof value === 'boolean'

const labelFor = (key: string) => (LABELLED[key] && te(LABELLED[key]) ? t(LABELLED[key]) : key)

/** Top-level scalar fields (known first, then unknown) offered as inputs. */
const scalarKeys = computed(() => {
  const d = draft.value
  if (!d) return []
  return KNOWN_KEYS.filter(key => key !== 'preview' && isScalar(d[key]))
})
const unknownKeys = computed(() => {
  const d = draft.value
  if (!d) return []
  return Object.keys(d).filter(key => !KNOWN_KEYS.includes(key))
})
const previewKeyList = computed(() => {
  const d = draft.value
  if (!d || !('preview' in d)) return []
  return ['preview']
})

const previewText = computed(() => {
  const list = draft.value?.preview
  if (Array.isArray(list)) return list.join('\n')
  return typeof list === 'string' ? list : ''
})
const setPreviewText = (value: string) => {
  if (!draft.value) return
  draft.value.preview = value
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
}

/** Inputs bind strings; nulls in the front-matter would break v-model. */
const sanitize = (obj: Record<string, any>): Record<string, any> => {
  for (const [key, value] of Object.entries(obj)) {
    if (value === null) obj[key] = ''
    else if (value && typeof value === 'object' && !Array.isArray(value)) sanitize(value)
  }
  return obj
}

const requestEdit = () => {
  confirm.require({
    message: t('informationEditWarning'),
    header: t('informationEdit'),
    icon: 'pi pi-info-circle',
    rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
    acceptProps: { label: t('informationEdit') },
    accept: () => {
      draft.value = sanitize(structuredClone(parseFrontmatter(description.value) ?? {}))
      editing.value = true
    },
    reject: () => {},
  })
}

const applyDraft = () => {
  if (!draft.value) return
  description.value = writeFrontmatter(description.value ?? '', draft.value)
  editing.value = false
  draft.value = null
}
</script>
