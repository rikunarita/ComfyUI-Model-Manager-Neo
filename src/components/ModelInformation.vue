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

    <table v-if="rows.length && !editing" class="w-full border-collapse border border-mm-border">
      <tbody>
        <tr v-for="row in rows" :key="row.id" class="h-8 border-b border-mm-border">
          <td
            class="w-40 border-r border-mm-border bg-mm-fg/6 px-4 text-mm-muted-fg backdrop-blur-sm"
          >
            {{ labelOf(row) }}
          </td>
          <td class="px-4 break-all text-mm-fg">
            <InformationValue :row="row" />
          </td>
        </tr>
      </tbody>
    </table>

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
      Tensor table: the exact tensor layout of the safetensors header
      (name / dtype / shape), rendered like Hugging Face's safetensors
      viewer. Only local safetensors models carry it; very large headers
      render paginated with an explicit expand action.
    -->
    <div v-if="tensors.length && !editing" class="flex flex-col gap-2">
      <div class="flex items-baseline justify-between gap-2">
        <div class="text-sm font-medium text-mm-muted-fg">{{ $t('info.tensors') }}</div>
        <div class="text-xs text-mm-muted-fg">{{ tensorsSummary }}</div>
      </div>
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
            <tr
              v-for="tensor in visibleTensors"
              :key="tensor.name"
              class="h-7 border-b border-mm-border last:border-b-0"
            >
              <td class="px-4 break-all text-mm-fg">{{ tensor.name }}</td>
              <td class="px-4 text-mm-muted-fg">{{ tensor.dtype }}</td>
              <td class="px-4 text-mm-muted-fg">{{ formatShape(tensor.shape) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <Button
        v-if="tensors.length > TENSOR_PAGE"
        variant="secondary"
        size="sm"
        class="self-start"
        @click="tensorsExpanded = !tensorsExpanded"
      >
        {{
          tensorsExpanded
            ? $t('info.tensorsShowLess')
            : $t('info.tensorsShowAll', { count: tensors.length })
        }}
      </Button>
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
import { Info, Pencil } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import InformationValue from 'components/InformationValue.vue'
import { Button } from 'components/ui/button'
import { Input } from 'components/ui/input'
import { useModelDescription, useModelMetadata } from 'hooks/model'
import { useToast } from 'hooks/toast'
import { type BaseModel, type SafetensorsTensor } from 'types/typings'
import {
  type InformationRow,
  buildInformationRows,
  parseFrontmatter,
  writeFrontmatter,
} from 'utils/modelInformation'

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

/**
 * Raw file metadata (safetensors `__metadata__`). Download search results
 * carry the Civitai *file* metadata here, which the parsed table above
 * already renders - showing it twice (including the `isRequired` / `size`
 * keys the table deliberately omits) would only be noise.
 */
const rawRows = computed(() => {
  const source = metadata.value
  if (!source || (model.value as any).downloadPlatform) return []
  const entries = Object.entries(source)
  if (!entries.length) return []
  return entries.map(([key, value]) => ({ key, value: stringify(value) }))
})

/* ---- tensor table (safetensors header) ---------------------------------- */

/** Rows rendered before the explicit "show all" expansion. */
const TENSOR_PAGE = 500
const tensorsExpanded = ref(false)

const tensors = computed<SafetensorsTensor[]>(() => {
  const list = (model.value as BaseModel).tensors
  return Array.isArray(list) ? list : []
})

const visibleTensors = computed(() =>
  tensorsExpanded.value ? tensors.value : tensors.value.slice(0, TENSOR_PAGE),
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
  const params = tensors.value.reduce(
    (total, tensor) => total + (tensor.shape ?? []).reduce((acc, dim) => acc * dim, 1),
    0,
  )
  return t('info.tensorsSummary', {
    count: tensors.value.length,
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
