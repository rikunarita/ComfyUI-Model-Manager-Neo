<template>
  <!--
    LAYOUT FIX: the window body (`min-h-0 flex-1 overflow-auto`) is the only
    scroller now. The old extra `h-full` + inner virtual `ResponseScroll`
    made the content column taller than the body (100% height *plus* the
    URL / version rows) so the editor fought the outer scrollbar and could
    end up clipped, displaced or invisible. Plain flow content in a single
    scrolling column cannot break that way.
  -->
  <div class="flex flex-col gap-4 px-5 pb-5">
    <ResponseInput
      v-model="modelUrl"
      :allow-clear="true"
      update-trigger="input"
      :placeholder="$t('pleaseInputModelUrl')"
      @keydown.enter="handleEnter"
    >
      <template #suffix>
        <!--
          BUG FIX: was `<span class="pi pi-search text-base opacity-60">`.
          PrimeIcons is gone, so the span rendered empty — the button that
          starts the Civitai / Hugging Face / direct-link search was never drawn
          at all (only the Enter key still worked). Lucide `Search` restores it.
        -->
        <Search class="size-4 cursor-pointer opacity-60" @click="handleEnter" />
      </template>
    </ResponseInput>

    <!-- Connected Civitai account (token check, like the hub whoami rows). -->
    <div v-if="civitaiAccount" class="-mt-2 text-xs text-mm-muted-fg">
      {{ $t('civitaiAccount') }}: {{ civitaiAccount }}
    </div>

    <!--
      Model-name search (any input that does not start with `https://`):
      parallel results from Hugging Face (left), ModelScope (middle) and
      Civitai (right). Rows carry the owner avatar in a rounded frame; the
      owner and repository halves of the id are deep links (hover underline,
      tap opens the page); clicking anywhere else resolves that model here.
    -->
    <div
      v-if="searchMode && searchResults && visiblePlatforms.length"
      class="grid gap-3 rounded-mm-ctl border border-mm-border bg-mm-fg/4 p-3"
      :style="{ gridTemplateColumns: `repeat(${visiblePlatforms.length}, minmax(0, 1fr))` }"
    >
      <div v-for="platform in visiblePlatforms" :key="platform" class="flex min-w-0 flex-col gap-2">
        <div class="flex items-center justify-between gap-2 text-xs text-mm-muted-fg">
          <span class="font-medium">{{ platformLabel(platform) }}</span>
          <span
            v-if="searchErrors[platform]"
            class="truncate text-mm-warning"
            :title="searchErrors[platform]"
          >
            {{ $t('searchFailed') }}
          </span>
        </div>
        <div class="flex min-h-0 flex-col gap-1 overflow-y-auto">
          <div
            v-for="item in searchItems[platform] ?? []"
            :key="item.key"
            class="flex cursor-pointer items-center gap-2 rounded-mm-ctl border border-transparent p-1 hover:border-mm-border hover:bg-mm-fg/8"
            :title="item.title"
            @click="selectSearchResult(item)"
          >
            <img
              v-if="item.avatar"
              :src="item.avatar"
              alt=""
              class="size-8 shrink-0 rounded-mm-ctl border border-mm-border object-cover"
            />
            <span
              v-else
              class="grid size-8 shrink-0 place-items-center rounded-mm-ctl border border-mm-border bg-mm-accent/25 text-xs font-bold text-mm-fg"
            >
              {{ (item.owner || '?').slice(0, 1).toUpperCase() }}
            </span>
            <div class="min-w-0 flex-1 text-sm">
              <div class="truncate">
                <a
                  class="cursor-pointer hover:underline"
                  :title="item.ownerUrl"
                  @click.stop.prevent="openExternal(item.ownerUrl)"
                  >{{ item.owner }}</a
                >/<a
                  class="cursor-pointer hover:underline"
                  :title="item.pageUrl"
                  @click.stop.prevent="openExternal(item.pageUrl)"
                  >{{ item.repo }}</a
                >
              </div>
              <div class="truncate text-xs text-mm-muted-fg">
                {{ $t('downloads') }}: {{ item.downloads }}
              </div>
            </div>
          </div>
          <div v-if="!(searchItems[platform] ?? []).length" class="p-1 text-xs text-mm-muted-fg">
            {{ $t('searchNoResults') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Direct file URL indicator with folder selection -->
    <div v-if="isDirectFile && modelUrl" class="flex flex-col gap-2">
      <div
        class="flex items-center gap-2 rounded-mm-ctl border border-mm-success/25 bg-mm-success/12 p-2 text-sm text-mm-success backdrop-blur-sm"
      >
        <!-- BUG FIX: `pi pi-check-circle` rendered empty (PrimeIcons removed). -->
        <CheckCircle class="size-4 shrink-0" />
        <span>{{ $t('directFileDetected') }}</span>
      </div>

      <!-- Model Type/Folder Selection for direct downloads (REQUIRED) -->
      <div class="flex items-center gap-2">
        <label class="text-sm font-medium">{{ $t('modelType') }}:</label>
        <ResponseSelect
          v-model="selectedModelType"
          :items="modelTypeOptions"
          :type="'drop'"
          class="flex-1"
          required
        />
      </div>

      <!-- Custom Subfolder Input (NEW) -->
      <div class="flex items-center gap-2">
        <label class="text-sm font-medium">{{ $t('subfolderOptional') }}</label>
        <ResponseInput
          v-model="customSubFolder"
          :placeholder="$t('subfolderPlaceholder')"
          class="flex-1"
        />
      </div>
    </div>

    <div v-show="data.length > 0">
      <ResponseSelect
        v-model="current"
        class="w-full"
        :items="data"
        :type="isMobile ? 'drop' : 'button'"
      >
        <template #prefix>
          <span>{{ $t('version') }}</span>
        </template>
      </ResponseSelect>
      <!-- Pre-download free-space guard read-out (backend enforces too). -->
      <div
        v-if="freeSpace !== null && currentModel"
        class="mt-1 text-xs"
        :class="(currentModel.sizeBytes || 0) > freeSpace ? 'text-mm-danger' : 'text-mm-muted-fg'"
      >
        {{ $t('freeSpace', { size: bytesToSize(freeSpace) }) }}
        <span v-if="(currentModel.sizeBytes || 0) > freeSpace">— {{ $t('notEnoughSpace') }}</span>
      </div>

      <!--
        Dry-run style plan of the pending task: where the file will land, its
        announced size, the published SHA256 (verified on completion for
        Civitai) and whether the platform API key is configured.
      -->
      <div
        v-if="downloadPlan"
        class="mt-2 flex flex-col gap-1 rounded-mm-ctl border border-mm-border bg-mm-fg/4 p-2 text-xs text-mm-muted-fg"
      >
        <div class="flex justify-between gap-2">
          <span class="shrink-0">{{ $t('planTarget') }}</span>
          <span class="truncate text-mm-fg" :title="downloadPlan.target">{{
            downloadPlan.target
          }}</span>
        </div>
        <div class="flex justify-between gap-2">
          <span class="shrink-0">{{ $t('planSize') }}</span>
          <span class="text-mm-fg">{{ downloadPlan.size }}</span>
        </div>
        <div v-if="downloadPlan.sha" class="flex justify-between gap-2">
          <span class="shrink-0">{{ $t('planHash') }}</span>
          <span class="truncate font-mono text-mm-fg" :title="downloadPlan.sha">
            {{ downloadPlan.sha.slice(0, 16) }}…
          </span>
        </div>
        <div class="flex justify-between gap-2">
          <span class="shrink-0">{{ $t('planAuth') }}</span>
          <span :class="downloadPlan.authOk ? 'text-mm-success' : 'text-mm-warning'">
            {{ downloadPlan.authLabel }}
          </span>
        </div>
      </div>

      <!-- Base-model family mismatch against the destination folder's library. -->
      <div
        v-if="baseMismatchWarning"
        class="mt-2 rounded-mm-ctl border border-mm-warning/30 bg-mm-warning/12 p-2 text-sm text-mm-warning backdrop-blur-sm"
      >
        {{ baseMismatchWarning }}
      </div>

      <!-- Pickle / archive payloads can execute code when loaded. -->
      <div
        v-if="executableWarning"
        class="mt-2 rounded-mm-ctl border border-mm-danger/30 bg-mm-danger/12 p-2 text-sm text-mm-danger backdrop-blur-sm"
      >
        {{ $t('execWarning') }}
      </div>
    </div>

    <KeepAlive>
      <ModelContent
        v-if="currentModel"
        :key="`${currentModel.id}-${currentModel.currentFileId}`"
        :model="currentModel"
        :editable="true"
        layout="stacked"
        @submit="(data: any) => createDownTask(data)"
      >
        <template #action>
          <div v-if="currentModel.files" class="flex-1">
            <ResponseSelect
              :model-value="currentModel.currentFileId"
              :items="currentModel.selectionFiles"
              :type="isMobile ? 'drop' : 'button'"
            >
            </ResponseSelect>
          </div>
          <!--
                BUG FIX: this button carried BOTH `type="submit"` and an
                `@click="createDownTask(currentModel)"` handler. It lives inside
                ModelContent's `<form @submit.prevent="handleSubmit">`, so one
                click fired twice:
                  1. @click  -> createDownTask(currentModel)  (raw, UNEDITED model)
                  2. submit  -> createDownTask(formData)      (the edited form data)
                Two download tasks were created for a single click. The second
                one failed with "File already exists: ..." (or, when they raced,
                two tasks downloaded the same file into different
                `<task>.download` files and both tried to move onto the same
                model path), and the first one ignored every edit made in the
                model editor (preview choice, description, type / sub-folder).
                Upstream only had `type="submit"`; restoring that keeps the
                single, form-driven path so the editor's values are honoured.
                `:disabled` still blocks the submit for a direct link with no
                model type chosen (a disabled button never submits).
              -->
          <Button type="submit" :disabled="isDirectFile && !selectedModelType">
            <Download class="size-4" />
            {{ $t('download') }}
          </Button>
        </template>
      </ModelContent>
    </KeepAlive>

    <div v-show="data.length === 0">
      <div class="flex flex-col items-center gap-4 py-8">
        <!-- BUG FIX: `pi pi-box` rendered empty (PrimeIcons removed). -->
        <Box class="size-8 opacity-60" />
        <div>{{ $t('noModelsFound') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Box, CheckCircle, Download, Search } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ModelContent from 'components/ModelContent.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import { useConfig } from 'hooks/config'
import { useDialog } from 'hooks/dialog'
import { useModelSearch } from 'hooks/download'
import { useLoading } from 'hooks/loading'
import { useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { app } from 'scripts/comfyAPI'
import { type VersionModel, type WithResolved } from 'types/typings'
import { bytesToSize, isDirectFileUrl, previewUrlToFile } from 'utils/common'
import { parseFrontmatter } from 'utils/modelInformation'

const { isMobile } = useConfig()
const { t, te } = useI18n()
const { toast } = useToast()
const loading = useLoading()
const dialog = useDialog()

const modelUrl = ref<string>()

// Model type selection for direct downloads (REQUIRED, no default)
const selectedModelType = ref<string>()

// Custom subfolder input (NEW)
const customSubFolder = ref<string>('')

/**
 * Pretty label for a model-folder key, translated through the
 * `modelTypeLabel.*` namespace. Folder keys ComfyUI (or another extension)
 * adds that this bundle has never heard of render as-is, so the list can never
 * show a blank entry.
 */
const modelTypeLabel = (type: string) =>
  te(`modelTypeLabel.${type}`) ? t(`modelTypeLabel.${type}`) : type

/**
 * BUG FIX: this used to be a hard-coded catalogue of every model type ComfyUI
 * *can* know about. Selecting a type the running ComfyUI has no folder for
 * (trivially easy: "GLIGEN", "Classifiers", "PhotoMaker", ...) only failed
 * later, at task-creation time, with "PathIndex 0 is not in <type>" - from the
 * user's side the Download click just appeared to do nothing. A download can
 * only ever be placed into a folder that exists, so only existing folders are
 * offered now (labels kept for the well-known keys).
 */
const modelTypeOptions = computed(() =>
  Object.keys(folders.value).map(type => {
    return {
      label: modelTypeLabel(type),
      value: type,
      command: () => {
        selectedModelType.value = type
      },
    }
  }),
)

const isDirectFile = computed(() => (modelUrl.value ? isDirectFileUrl(modelUrl.value) : false))

const { current, currentModel, data, search } = useModelSearch()
const { folders, data: modelsData } = useModels()

/* ---- model-name search (input without `https://` prefix) ---------------- */
const searchMode = computed(() => {
  const url = modelUrl.value
  if (!url) return false
  return !url.startsWith('https://')
})
const searchResults = ref<Record<string, { items: SearchItem[]; error?: string }> | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | undefined

interface SearchItem {
  platform: string
  key: string
  owner: string
  repo: string
  title: string
  downloads: number
  avatar: string | null
  pageUrl: string
  ownerUrl: string
}

// Real-time `https://` prefix check: while the prefix is not (yet) typed the
// field behaves as a search box; once it is, it behaves as a URL field.
watch(modelUrl, value => {
  clearTimeout(searchTimer)
  if (!value || value.startsWith('https://')) {
    searchResults.value = null
    return
  }
  searchTimer = setTimeout(() => void runModelSearch(value), 400)
})

const runModelSearch = async (query: string) => {
  try {
    searchResults.value = await request(`/search?query=${encodeURIComponent(query)}&limit=8`)
  } catch (error) {
    searchResults.value = null
    toast.add({ severity: 'error', detail: (error as Error).message, life: 6000 })
  }
}

const PLATFORM_HIDE_SETTING: Record<string, string> = {
  hf: 'ModelManager.Search.HideHuggingFace',
  modelscope: 'ModelManager.Search.HideModelScope',
  civitai: 'ModelManager.Search.HideCivitai',
}
const visiblePlatforms = computed(() =>
  ['hf', 'modelscope', 'civitai'].filter(
    platform =>
      !(app.ui?.settings.getSettingValue<boolean>(PLATFORM_HIDE_SETTING[platform]) ?? false),
  ),
)
const searchItems = computed(() => {
  const out: Record<string, SearchItem[]> = {}
  for (const platform of visiblePlatforms.value) {
    out[platform] = searchResults.value?.[platform]?.items ?? []
  }
  return out
})
const searchErrors = computed(() => {
  const out: Record<string, string> = {}
  for (const platform of visiblePlatforms.value) {
    const error = searchResults.value?.[platform]?.error
    if (error) out[platform] = error
  }
  return out
})
const platformLabel = (platform: string) =>
  platform === 'hf' ? t('providerHf') : platform === 'modelscope' ? t('providerMs') : t('civitai')
const openExternal = (url: string) => window.open(url, '_blank')
const selectSearchResult = (item: SearchItem) => {
  searchResults.value = null
  modelUrl.value = item.pageUrl
  void searchModelsByUrl()
}

const REPO_ID_RE = /^[\w.-]+\/[\w.-]+$/
/** Enter / search icon: URL mode resolves; search mode picks or re-searches. */
const handleEnter = () => {
  const value = (modelUrl.value ?? '').trim()
  if (!value) return
  if (!searchMode.value) return void searchModelsByUrl()
  const lowered = value.toLowerCase()
  const exact = Object.values(searchItems.value)
    .flat()
    .find(item => item.key.toLowerCase() === lowered || item.title.toLowerCase() === lowered)
  if (exact) return selectSearchResult(exact)
  // `username/repo-name` without a scheme resolves straight to the HF repo.
  if (REPO_ID_RE.test(value)) {
    modelUrl.value = `https://huggingface.co/${value}`
    return void searchModelsByUrl()
  }
  return void runModelSearch(value)
}

/* ---- civitai account + download plan + warnings ------------------------- */
const authStatus = ref<Record<string, boolean>>({})
const civitaiAccount = ref<string>()

onMounted(async () => {
  try {
    authStatus.value = (await request('/auth-status')) ?? {}
  } catch {
    authStatus.value = {}
  }
  if (authStatus.value.civitai) {
    try {
      const me = await request('/civitai/whoami')
      civitaiAccount.value = me?.name || undefined
    } catch {
      civitaiAccount.value = undefined
    }
  }
})

const downloadPlan = computed(() => {
  const model = currentModel.value
  if (!model || !model.type) return null
  const base = folders.value[model.type]?.[model.pathIndex ?? 0]
  if (!base) return null
  const sub = model.subFolder ? `${model.subFolder}/` : ''
  const platform = String((model as any).downloadPlatform ?? '').toLowerCase()
  const authKey =
    platform === 'civitai'
      ? 'civitai'
      : platform === 'huggingface'
        ? 'hf'
        : platform === 'modelscope'
          ? 'modelscope'
          : null
  return {
    target: `${base}/${sub}${model.basename}${model.extension}`,
    size: bytesToSize(model.sizeBytes),
    sha: ((model as any).hashes as Record<string, string> | undefined)?.SHA256 || null,
    authOk: authKey ? Boolean(authStatus.value[authKey]) : true,
    authLabel: authKey
      ? `${platformLabel(authKey)}: ${authStatus.value[authKey] ? t('authSet') : t('authUnset')}`
      : t('authUnneeded'),
  }
})

/** Version baseModel vs the base models recorded in the destination folder. */
const baseMismatchWarning = computed(() => {
  const model = currentModel.value
  if (!model?.type || !model.description) return null
  const front = parseFrontmatter(model.description)
  const versionBase = typeof front?.baseModel === 'string' ? front.baseModel : null
  if (!versionBase) return null
  const bases = new Set<string>()
  for (const item of modelsData.value[model.type] ?? []) {
    if (!item.isFolder && item.modelBase) bases.add(item.modelBase)
  }
  if (bases.size < 3 || bases.has(versionBase)) return null
  return t('baseMismatch', { version: versionBase, folder: [...bases].slice(0, 3).join(', ') })
})

const EXECUTABLE_EXTS = [
  '.ckpt',
  '.pt',
  '.pth',
  '.bin',
  '.pickle',
  '.pkl',
  '.zip',
  '.tar',
  '.gz',
  '.tgz',
  '.rar',
  '.7z',
]
const executableWarning = computed(() => {
  const model = currentModel.value
  if (!model) return false
  const name = `${model.basename}${model.extension}`.toLowerCase()
  return EXECUTABLE_EXTS.some(ext => name.endsWith(ext))
})

const searchModelsByUrl = async () => {
  if (modelUrl.value) {
    const modelType = isDirectFile.value ? selectedModelType.value : undefined
    await search(modelUrl.value, modelType)
  }
}

// Watch for direct file URL changes (NO auto-detection anymore)
watch(modelUrl, () => {
  // Reset direct-file state on every URL change so a stale model type or
  // custom sub-folder can never leak into the next search/download
  // (previously the state survived a switch to a non-direct URL).
  selectedModelType.value = undefined
  customSubFolder.value = ''
})

// Watch for model type changes on direct files and refresh the model
watch(selectedModelType, async () => {
  if (isDirectFile.value && modelUrl.value && selectedModelType.value) {
    await search(modelUrl.value, selectedModelType.value)
  }
})

/**
 * Append the preview gallery as previewFile / previewFile2 / ... multipart
 * fields, converting each URL to a File in the browser when possible.
 */
const appendPreviewFields = async (formData: FormData, value: unknown) => {
  const gallery = Array.isArray(value) ? value : value ? [value] : []
  if (gallery.length === 0) {
    // No preview: send an empty string (the backend's "nothing to do"
    // sentinel) instead of stringifying `undefined`.
    formData.append('previewFile', (value as string) ?? '')
    return
  }
  let fieldIndex = 0
  for (const item of gallery) {
    fieldIndex += 1
    const field = fieldIndex === 1 ? 'previewFile' : `previewFile${fieldIndex}`
    const previewFile = await previewUrlToFile(item).catch(() => null)
    if (previewFile) {
      formData.append(field, previewFile)
      continue
    }
    // BUG FIX: the browser-side preview fetch can fail (CORS, hotlink
    // protection, offline CDN, ...). Aborting the whole submission made the
    // Download click look completely dead - no dialog change, no task. Hand
    // the raw URL to the backend instead: save_model_preview() downloads it
    // server-side, where CORS does not exist, and degrades to "no preview"
    // if that fails too.
    toast.add({
      severity: 'warn',
      summary: t('warning'),
      detail: t('previewFetchFallback'),
      life: 5000,
    })
    formData.append(field, item)
  }
}

const freeSpace = ref<number | null>(null)

watch(
  currentModel,
  async model => {
    if (!model?.type) {
      freeSpace.value = null
      return
    }
    try {
      const result = await request(`/disk-free/${model.type}/${model.pathIndex ?? 0}`)
      freeSpace.value = result?.free ?? null
    } catch {
      freeSpace.value = null
    }
  },
  { immediate: true },
)

const createDownTask = async (data: WithResolved<VersionModel>) => {
  // type が未選択の場合は送信を拒否
  if (!data.type) {
    toast.add({
      severity: 'warn',
      summary: t('warning'),
      detail: t('selectModelTypeFirst'),
      life: 5000,
    })
    return
  }
  loading.show()

  // Resolve the effective sub-folder exactly once.
  // BUG FIX: previously the payload's own `subFolder` (empty for direct-file
  // downloads) was appended first and the custom value appended second; the
  // backend reads `dict(MultiDict)` which keeps the FIRST value, so the custom
  // sub-folder was silently dropped. A sub-folder chosen in the model editor
  // takes precedence, otherwise the optional direct-download input is used.
  const payload: WithResolved<VersionModel> = { ...data }
  if (!payload.subFolder && customSubFolder.value?.trim()) {
    payload.subFolder = customSubFolder.value.trim()
  }

  const formData = new FormData()
  for (const key in payload) {
    if (Object.hasOwn(payload, key)) {
      let value = (payload as any)[key]

      // set preview file(s): the editor hands over the whole gallery now
      if (key === 'preview') {
        await appendPreviewFields(formData, value)
        continue
      }

      if (typeof value === 'object') {
        value = JSON.stringify(value)
      }

      if (typeof value === 'number') {
        value = value.toString()
      }

      formData.append(key, value)
    }
  }

  // BUG FIX: `fullname` must be the file name relative to the sub-folder.
  // The backend joins `subFolder` + `fullname` itself, so sending the already
  // joined `genModelFullName()` produced a doubled prefix
  // (`sub/sub/file.safetensors`) whenever a sub-folder was set.
  formData.set('fullname', `${payload.basename}${payload.extension}`)

  await request('/model', {
    method: 'POST',
    body: formData,
  })
    .then(() => {
      dialog.close()
    })
    .catch(e => {
      toast.add({
        severity: 'error',
        summary: t('error'),
        detail: e.message ?? t('failedToCreateDownloadTask'),
        life: 15000,
      })
    })
    .finally(() => {
      loading.hide()
    })
}
</script>
