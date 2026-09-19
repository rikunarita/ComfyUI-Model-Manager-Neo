<template>
  <div class="h-full px-4">
    <Tabs v-model="stepValue" class="flex h-full flex-col" default-value="platform">
      <!-- Folder batch mode jumps straight to the upload form. -->
      <div
        v-if="folderMode"
        class="rounded-mm-ctl border border-mm-border bg-mm-fg/6 px-3 py-2 text-sm"
      >
        {{ $t('hfUpload.folderBatch', { n: files?.length ?? 0 }) }}
      </div>
      <!--
        The wizard always starts at the upload PLATFORM (both modes); the
        folder batch flow then goes straight to the form, the single-model
        flow continues through type and model selection.
      -->
      <TabsList v-if="folderMode" class="grid w-full grid-cols-2">
        <TabsTrigger value="platform">{{ $t('selectPlatform') }}</TabsTrigger>
        <TabsTrigger value="upload" :disabled="stepValue === 'platform'">{{
          $t('upload')
        }}</TabsTrigger>
      </TabsList>
      <TabsList v-else class="grid w-full grid-cols-4">
        <TabsTrigger value="platform">{{ $t('selectPlatform') }}</TabsTrigger>
        <TabsTrigger value="type" :disabled="stepValue === 'platform'">{{
          $t('selectModelType')
        }}</TabsTrigger>
        <TabsTrigger value="model" :disabled="stepValue === 'platform' || stepValue === 'type'">{{
          $t('selectModel')
        }}</TabsTrigger>
        <TabsTrigger
          value="upload"
          :disabled="stepValue === 'platform' || stepValue === 'type' || stepValue === 'model'"
          >{{ $t('upload') }}</TabsTrigger
        >
      </TabsList>

      <!-- Step: upload platform -->
      <TabsContent value="platform" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col items-center justify-center gap-4">
          <div class="text-sm text-mm-muted-fg">{{ $t('selectPlatformHint') }}</div>
          <div class="flex gap-4">
            <Button
              size="lg"
              :variant="provider === 'hf' ? 'default' : 'secondary'"
              :title="$t('providerHf')"
              @click="chooseProvider('hf')"
            >
              {{ $t('providerHf') }}
            </Button>
            <Button
              size="lg"
              :variant="provider === 'modelscope' ? 'default' : 'secondary'"
              :title="$t('providerMs')"
              @click="chooseProvider('modelscope')"
            >
              {{ $t('providerMs') }}
            </Button>
          </div>
        </div>
      </TabsContent>

      <!-- Step: Select model type -->
      <TabsContent value="type" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col overflow-hidden">
          <ModelTypeButtonGrid :items="typeOptions" class="min-h-0 flex-1" />
          <div class="flex justify-between pt-6">
            <Button variant="secondary" @click="stepValue = 'platform'">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
          </div>
        </div>
      </TabsContent>

      <!-- Step: Select model -->
      <TabsContent value="model" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col overflow-hidden">
          <ResponseScroll class="flex-1">
            <div
              v-if="modelList.length === 0"
              class="flex flex-col items-center gap-4 py-8 opacity-60"
            >
              <!-- BUG FIX: `pi pi-box` rendered empty (PrimeIcons removed). -->
              <Box class="size-8 opacity-60" />
              <div>{{ $t('noModelsInCurrentPath') }}</div>
            </div>
            <div v-else class="grid grid-cols-3 gap-4 md:grid-cols-4">
              <div
                v-for="model in modelList"
                :key="genModelKey(model)"
                class="cursor-pointer overflow-hidden rounded-lg border border-mm-border"
                @click="handleSelectModel(model)"
              >
                <div class="preview-aspect w-full">
                  <img :src="getPreviewUrl(model.preview)" class="size-full object-cover" />
                </div>
                <div class="truncate p-2 text-sm">
                  {{ model.basename }}
                </div>
              </div>
            </div>
          </ResponseScroll>
          <div class="flex justify-between pt-6">
            <Button variant="secondary" @click="handleBackTypeSelect">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
          </div>
        </div>
      </TabsContent>

      <!-- Step: upload form -->
      <TabsContent value="upload" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col gap-4 overflow-hidden">
          <ResponseScroll class="min-h-0 flex-1">
            <div class="flex flex-col gap-4 py-2">
              <div v-if="folderMode" class="rounded-lg border border-mm-border p-3">
                <div class="font-bold">
                  {{ $t('hfUpload.folderBatch', { n: files?.length ?? 0 }) }}
                </div>
                <div class="text-sm opacity-60">
                  {{ formatSize(folderTotalSize) }}
                </div>
                <div class="mt-2 flex max-h-28 flex-col gap-0.5 overflow-y-auto text-xs opacity-70">
                  <div v-for="file in files" :key="file.fullname" class="truncate">
                    {{ file.fullname }}
                  </div>
                </div>
              </div>
              <div v-else class="rounded-lg border border-mm-border p-3">
                <div class="truncate font-bold">
                  {{ selectedModel?.basename }}{{ selectedModel?.extension }}
                </div>
                <div class="text-sm opacity-60">
                  {{ selectedModel?.type }} · {{ formatSize(selectedModel?.sizeBytes) }}
                </div>
              </div>
              <div v-if="whoamiName" class="text-sm opacity-60">
                {{ provider === 'hf' ? $t('providerHf') : $t('providerMs') }}
                {{ $t('account') }}: {{ whoamiName }}
              </div>
              <div
                v-if="whoamiError"
                class="rounded-mm-ctl border border-mm-warning/30 bg-mm-warning/12 p-2 text-sm text-mm-warning backdrop-blur-sm"
              >
                {{ whoamiError }}
              </div>
              <div class="flex flex-col gap-2">
                <label class="text-sm font-medium">{{ $t('repoId') }}</label>
                <Input v-model="repoId" placeholder="username/repo-name" />
              </div>
              <div class="flex items-center gap-2">
                <Checkbox id="hf-private-repo" v-model="privateRepo" />
                <label for="hf-private-repo" class="text-sm">
                  {{ $t('privateRepoIfCreate') }}
                </label>
              </div>
              <div class="flex items-center gap-2">
                <Checkbox id="rename-notes-readme" v-model="renameNotes" />
                <label
                  for="rename-notes-readme"
                  class="text-sm"
                  :title="$t('renameNotesToReadmeHint')"
                >
                  {{ $t('renameNotesToReadme') }}
                </label>
              </div>
              <div class="flex items-center gap-2">
                <Checkbox id="include-related-assets" v-model="includeAssets" />
                <label
                  for="include-related-assets"
                  class="text-sm"
                  :title="$t('includeAssetsHint')"
                >
                  {{ $t('includeAssets') }}
                </label>
              </div>
              <div class="flex flex-col gap-2">
                <label class="text-sm font-medium">{{ $t('pathInRepo') }}</label>
                <Input v-model="pathInRepo" placeholder="folder/model.safetensors" />
              </div>
            </div>
          </ResponseScroll>
          <div v-show="hfUpload.active" class="w-full">
            <!--
              BUG FIX: the backend can only report 0% and then 100%
              (huggingface_hub exposes no per-chunk callback), so the bar sat at
              a motionless 0% for the whole transfer. Render it indeterminate
              until a real percentage arrives; `Progress` already supports the
              mode. The state lives in `hooks/hfUpload`, so the bar keeps
              showing (and re-appears on re-open) while the transfer runs.
              The transfer itself now streams accurate percentages through a
              progress-reporting file wrapper (py/upload_hf.py), shown both in
              the bar and in the read-out next to it.

              BUG FIX: the read-out also names the phase. Hashing a
              multi-gigabyte checkpoint locally takes minutes before a single
              byte leaves the machine, and a bar that never moved during it is
              exactly what reads as "the upload never started".
            -->
            <div class="mb-1 flex items-center justify-between gap-2 text-xs text-mm-muted-fg">
              <span data-hf-phase>{{ phaseLabel }}</span>
              <span v-if="hfUpload.phase === 'hash'" class="truncate opacity-70">
                {{ $t('hfUpload.hashHint') }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <Progress class="flex-1" :model-value="hfUpload.progress" :mode="barMode" />
              <span
                v-show="barMode === 'determinate'"
                class="w-10 text-right text-xs text-mm-muted-fg tabular-nums"
              >
                {{ hfUpload.progress }}%
              </span>
            </div>
          </div>
          <div class="flex justify-between pt-6">
            <Button variant="secondary" @click="handleBackModelSelect">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
            <span></span>
            <Button :disabled="!repoId || !pathInRepo || hfUpload.active" @click="handleUpload">
              <Upload class="size-4" />
              {{ $t('upload') }}
            </Button>
          </div>
        </div>
      </TabsContent>
    </Tabs>
  </div>
</template>

<script setup lang="ts">
import { Box, ChevronLeft, Upload } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ModelTypeButtonGrid from 'components/ModelTypeButtonGrid.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Checkbox } from 'components/ui/checkbox'
import { Input } from 'components/ui/input'
import { Progress } from 'components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { useDialog } from 'hooks/dialog'
import { hfUploadState, isFinishedTask, resetHfUploadState } from 'hooks/hfUpload'
import { useLoading } from 'hooks/loading'
import { genModelFullName, useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { type Model } from 'types/typings'
import { bytesToSize } from 'utils/common'
import { NO_PREVIEW_URL } from 'utils/media'
import { genModelKey } from 'utils/model'

interface Props {
  /** Folder batch mode: upload these files instead of a single selection. */
  files?: { type: string; pathIndex: number; fullname: string; sizeBytes?: number }[]
}
const props = defineProps<Props>()

const folderMode = computed(() => (props.files?.length ?? 0) > 0)
const folderTotalSize = computed(() =>
  (props.files ?? []).reduce((acc, f) => acc + (f.sizeBytes ?? 0), 0),
)

const { t } = useI18n()
const { toast } = useToast()
const loading = useLoading()
const dialog = useDialog()
// Optimization B-8: the model store already caches every folder it fetched,
// so re-opening this dialog (or switching back to a type) no longer
// re-requests the whole listing - it reads the cache and only fetches what
// is missing.
const { data: modelsCache, refreshFolder, visibleTypes } = useModels()

const stepValue = ref<'platform' | 'type' | 'model' | 'upload'>('platform')
const currentType = ref<string>()

const typeOptions = computed(() => {
  return visibleTypes().map(type => {
    return {
      label: type,
      value: type,
      command: () => {
        currentType.value = type
        stepValue.value = 'model'
        fetchModels(type)
      },
    }
  })
})

const modelList = ref<Model[]>([])

const fetchModels = async (type: string) => {
  const cached = modelsCache.value[type]
  if (cached) {
    modelList.value = cached.filter(item => !item.isFolder)
    return
  }
  loading.show()
  try {
    await refreshFolder(type)
    modelList.value = (modelsCache.value[type] ?? []).filter(item => !item.isFolder)
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: (error as Error).message,
      life: 5000,
    })
  } finally {
    loading.hide()
  }
}

const selectedModel = ref<Model>()

const handleSelectModel = (model: Model) => {
  selectedModel.value = model
  pathInRepo.value = genModelFullName(model)
  stepValue.value = 'upload'
}

/** Back from the model grid to the type grid. */
const handleBackTypeSelect = () => {
  selectedModel.value = undefined
  currentType.value = undefined
  modelList.value = []
  stepValue.value = 'type'
}

/** Back from the form: to the model grid, or to the platform step in batch mode. */
const handleBackModelSelect = () => {
  if (folderMode.value) {
    stepValue.value = 'platform'
    return
  }
  selectedModel.value = undefined
  stepValue.value = 'model'
}

const repoId = ref<string>()
const privateRepo = ref(false)
/** Also upload the model's sidecars (previews / notes) next to the model. */
const includeAssets = ref(false)
/** Commit the model's Markdown notes as the repository's README.md. */
const renameNotes = ref(true)
const pathInRepo = ref<string>()
const provider = ref<'hf' | 'modelscope'>('hf')

/**
 * Platform step: pick the hub and advance (batch mode jumps to the form,
 * the single-model flow to the type grid). Re-picking another platform
 * re-checks the account name for it.
 */
const chooseProvider = (next: 'hf' | 'modelscope') => {
  if (provider.value !== next) {
    provider.value = next
    whoamiName.value = undefined
    whoamiError.value = undefined
    void fetchWhoami()
  }
  // The window title names the chosen platform from here on.
  const item = dialog.stack.value.find(entry => entry.key === 'model-manager-hf-upload')
  if (item) item.title = t(next === 'hf' ? 'uploadToHf' : 'uploadToMs')
  stepValue.value = folderMode.value ? 'upload' : 'type'
}

const whoamiName = ref<string>()
const whoamiError = ref<string>()

const fetchWhoami = async () => {
  const picked = provider.value
  try {
    const route = picked === 'hf' ? '/hf/whoami' : '/modelscope/whoami'
    const result = await request(route)
    // A slow answer from the previous platform must not label the new one.
    if (provider.value !== picked) return
    whoamiName.value = result?.name
    whoamiError.value = undefined
  } catch (error) {
    if (provider.value !== picked) return
    whoamiName.value = undefined
    whoamiError.value = (error as Error).message
  }
}

/**
 * BUG FIX — the upload lifecycle no longer lives and dies with this dialog.
 *
 * Previously `POST /hf/upload` only answered after the WHOLE transfer and all
 * progress lived in local refs: ComfyUI's `api.fetchApi` aborts requests whose
 * response headers take longer than 60 s (multi-GB uploads always do), aiohttp
 * cancels handlers whose client goes away, and closing the dialog disposed
 * every piece of progress UI — from the user's side: "no progress bar, and
 * closing the window cancels the task".
 *
 * The backend now returns a task id immediately and runs the transfer as a
 * background task; progress / completion / errors are websocket events
 * handled module-wide in `hooks/hfUpload`, and the shared `hfUploadState`
 * survives closing and re-opening this dialog.
 */
const hfUpload = hfUploadState

/** Human-readable name of the phase the backend is currently in. */
const phaseLabel = computed(() => {
  const ns = hfUpload.provider === 'modelscope' ? 'msUpload' : 'hfUpload'
  return t(`${ns}.phase.${hfUpload.phase}`)
})

/**
 * `prepare` has no measurable percentage yet, so sweep instead of pinning the
 * bar to 0%; `hash` and `upload` both report real fractions.
 */
const barMode = computed<'determinate' | 'indeterminate'>(() =>
  hfUpload.phase === 'prepare' ||
  hfUpload.progress <= 0 ||
  (hfUpload.phase === 'upload' && !hfUpload.chunked)
    ? 'indeterminate'
    : 'determinate',
)

const handleUpload = async () => {
  if (!selectedModel.value && !folderMode.value) return
  resetHfUploadState()
  hfUpload.repoId = repoId.value ?? ''
  hfUpload.pathInRepo = pathInRepo.value ?? ''
  const uploadRoute = provider.value === 'hf' ? '/hf/upload' : '/modelscope/upload'
  const payload = folderMode.value
    ? {
        files: props.files,
        repoId: repoId.value,
        pathInRepo: pathInRepo.value,
        private: privateRepo.value,
        includeAssets: includeAssets.value,
        renameNotesToReadme: renameNotes.value,
      }
    : {
        type: selectedModel.value!.type,
        pathIndex: selectedModel.value!.pathIndex,
        fullname: genModelFullName(selectedModel.value!),
        repoId: repoId.value,
        pathInRepo: pathInRepo.value,
        private: privateRepo.value,
        includeAssets: includeAssets.value,
        renameNotesToReadme: renameNotes.value,
      }
  try {
    const result = await request(uploadRoute, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    // The transfer itself is tracked through the websocket events; the id
    // only lets this instance ignore events of an earlier upload. A very fast
    // upload (a duplicate short-circuit, or a Hub-side dedup that moves no
    // bytes) can complete before this response is read - writing its id back
    // would leave a stale filter in place for the next upload.
    const taskId = result?.taskId ?? null
    hfUpload.taskId = isFinishedTask(taskId) ? null : taskId
  } catch (error) {
    // The server rejected the upload BEFORE it started (missing token,
    // invalid path, ...). A started transfer reports its own failure through
    // `hf_upload_error`.
    hfUpload.active = false
    hfUpload.taskId = null
    hfUpload.progress = 0
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: error instanceof Error ? error.message : String(error),
      life: 15000,
    })
  }
}

const formatSize = (size?: number) => {
  return size ? bytesToSize(size) : t('unknown')
}

const getPreviewUrl = (preview: string | string[] | undefined): string => {
  // Never hand <img> an empty src: that resolves to the page URL, fails to
  // decode as an image and logs a console error. The glass NO-PREVIEW artwork
  // is the documented default for a model without a preview.
  if (!preview) return NO_PREVIEW_URL
  if (Array.isArray(preview)) return preview[0] || NO_PREVIEW_URL
  return preview
}

onMounted(() => {
  fetchWhoami()
})
</script>
