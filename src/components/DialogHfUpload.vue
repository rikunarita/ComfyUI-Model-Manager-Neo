<template>
  <div class="h-full px-4">
    <Tabs v-model="stepValue" class="flex h-full flex-col" default-value="1">
      <TabsList class="grid w-full grid-cols-3">
        <TabsTrigger value="1">{{ $t('selectModelType') }}</TabsTrigger>
        <TabsTrigger value="2" :disabled="stepValue === '1'">{{ $t('selectModel') }}</TabsTrigger>
        <TabsTrigger value="3" :disabled="stepValue === '1' || stepValue === '2'">{{
          $t('uploadToHuggingFace')
        }}</TabsTrigger>
      </TabsList>

      <!-- Step 1: Select model type -->
      <TabsContent value="1" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col overflow-hidden">
          <ResponseScroll>
            <div class="flex flex-wrap gap-4">
              <Button v-for="item in typeOptions" :key="item.value" @click="item.command">
                {{ item.label }}
              </Button>
            </div>
          </ResponseScroll>
        </div>
      </TabsContent>

      <!-- Step 2: Select model -->
      <TabsContent value="2" class="flex-1 overflow-hidden">
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

      <!-- Step 3: Upload to HuggingFace -->
      <TabsContent value="3" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col gap-4 overflow-hidden">
          <ResponseScroll class="min-h-0 flex-1">
            <div class="flex flex-col gap-4 py-2">
              <div class="rounded-lg border border-mm-border p-3">
                <div class="truncate font-bold">
                  {{ selectedModel?.basename }}{{ selectedModel?.extension }}
                </div>
                <div class="text-sm opacity-60">
                  {{ selectedModel?.type }} · {{ formatSize(selectedModel?.sizeBytes) }}
                </div>
              </div>
              <div v-if="whoamiName" class="text-sm opacity-60">
                {{ $t('hfAccount') }}: {{ whoamiName }}
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
              <div class="flex flex-col gap-2">
                <label class="text-sm font-medium">{{ $t('pathInRepo') }}</label>
                <Input v-model="pathInRepo" placeholder="folder/model.safetensors" />
              </div>
            </div>
          </ResponseScroll>
          <div v-show="uploading" class="w-full">
            <!--
              BUG FIX: the backend can only report 0% and then 100%
              (huggingface_hub exposes no per-chunk callback), so the bar sat at
              a motionless 0% for the whole transfer. Render it indeterminate
              until a real percentage arrives; `Progress` already supports the
              mode.
            -->
            <Progress
              :model-value="uploadProgress"
              :mode="uploadProgress > 0 ? 'determinate' : 'indeterminate'"
            />
          </div>
          <div class="flex justify-between pt-6">
            <Button variant="secondary" @click="handleBackModelSelect">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
            <Button :disabled="!repoId || !pathInRepo || uploading" @click="handleUpload">
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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Checkbox } from 'components/ui/checkbox'
import { Input } from 'components/ui/input'
import { Progress } from 'components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { configSetting } from 'hooks/config'
import { useLoading } from 'hooks/loading'
import { genModelFullName, useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { api, app } from 'scripts/comfyAPI'
import { type Model } from 'types/typings'
import { bytesToSize } from 'utils/common'
import { genModelKey } from 'utils/model'

const { toast } = useToast()
const loading = useLoading()
const { folders } = useModels()

const stepValue = ref('1')
const currentType = ref<string>()

const typeOptions = computed(() => {
  const excludeModelTypes = app.ui?.settings.getSettingValue<string>(
    configSetting.excludeModelTypes,
  )
  const customBlackList =
    excludeModelTypes
      ?.split(',')
      .map((type: string) => type.trim())
      .filter(Boolean) ?? []
  return Object.keys(folders.value)
    .filter(folder => !customBlackList.includes(folder))
    .map(type => {
      return {
        label: type,
        value: type,
        command: () => {
          currentType.value = type
          stepValue.value = '2'
          fetchModels(type)
        },
      }
    })
})

const modelList = ref<Model[]>([])

const fetchModels = async (type: string) => {
  loading.show()
  try {
    const resData = (await request(`/models/${type}`)) as Model[]
    modelList.value = (resData ?? []).filter(item => !item.isFolder)
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
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
  stepValue.value = '3'
}

const handleBackTypeSelect = () => {
  currentType.value = undefined
  modelList.value = []
  stepValue.value = '1'
}

const handleBackModelSelect = () => {
  selectedModel.value = undefined
  stepValue.value = '2'
}

const repoId = ref<string>()
const privateRepo = ref(false)
const pathInRepo = ref<string>()

const whoamiName = ref<string>()
const whoamiError = ref<string>()

const fetchWhoami = async () => {
  try {
    const result = await request('/hf/whoami')
    whoamiName.value = result?.name
  } catch (error) {
    whoamiError.value = (error as Error).message
  }
}

const uploading = ref(false)
const uploadProgress = ref(0)

/**
 * BUG FIX — "Upload to Hugging Face" reported a FALSE FAILURE for every real
 * model.
 *
 * `POST /hf/upload` only answers once the whole file has been transferred
 * (`upload_to_hf` awaits the executor). ComfyUI's `api.fetchApi` aborts any
 * request whose response headers have not arrived within 60 seconds
 * (`FETCH_RESPONSE_HEADERS_TIMEOUT_MS = 60_000` in ComfyUI_frontend
 * `src/scripts/api.ts`). Uploading a multi-GB model always exceeds that, so the
 * promise rejected with `DOMException: Fetch timeout`, the catch showed a red
 * "Error / Fetch timeout" toast and `finally` set `uploading = false` — which
 * also hid the progress bar — while the server carried on and uploaded the file
 * successfully (`update_hf_upload_progress` 100% + `hf_upload_complete` were
 * both emitted and simply ignored; nothing listened for the latter).
 *
 * Completion is now driven by the websocket events instead of the HTTP
 * round-trip. The POST's own rejection is still honoured, but ONLY when it is a
 * real server error: a client-side abort/timeout after the server acknowledged
 * the upload keeps the progress UI up and waits for `hf_upload_complete`.
 */

/** True once the server pushed its first progress event for this upload. */
const serverStarted = ref(false)
/** Guard so a late POST resolution cannot double-report success. */
const settled = ref(false)

/** ComfyUI aborts timed-out fetches with a DOMException named Timeout/Abort. */
const isClientAbort = (error: unknown) => {
  const name = (error as { name?: string } | null | undefined)?.name
  return name === 'TimeoutError' || name === 'AbortError'
}

const finishSuccess = (detail?: { repoId?: string; pathInRepo?: string }) => {
  if (settled.value) return
  settled.value = true
  uploading.value = false
  uploadProgress.value = 100
  toast.add({
    severity: 'success',
    summary: 'Success',
    detail: `${selectedModel.value?.basename ?? detail?.pathInRepo ?? ''} -> ${
      detail?.repoId ?? repoId.value ?? ''
    }`,
    life: 5000,
  })
}

const finishError = (message: string) => {
  if (settled.value) return
  settled.value = true
  uploading.value = false
  toast.add({ severity: 'error', summary: 'Error', detail: message, life: 15000 })
}

const handleUpload = async () => {
  if (!selectedModel.value) return
  uploading.value = true
  uploadProgress.value = 0
  serverStarted.value = false
  settled.value = false
  const payload = {
    type: selectedModel.value.type,
    pathIndex: selectedModel.value.pathIndex,
    fullname: genModelFullName(selectedModel.value),
    repoId: repoId.value,
    pathInRepo: pathInRepo.value,
    private: privateRepo.value,
  }
  try {
    await request('/hf/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    // Fast upload: the POST resolved before the client timeout. The websocket
    // `hf_upload_complete` normally wins the race; only finalise if it did not.
    finishSuccess()
  } catch (error) {
    if (isClientAbort(error) && serverStarted.value) {
      // The server is still uploading; `hf_upload_complete` will settle it.
      return
    }
    finishError(error instanceof Error ? error.message : String(error))
  }
}

const formatSize = (size?: number) => {
  return size ? bytesToSize(size) : 'Unknown'
}

const getPreviewUrl = (preview: string | string[] | undefined): string => {
  if (!preview) return ''
  if (Array.isArray(preview)) return preview[0] || ''
  return preview
}

const updateHfProgress = (event: CustomEvent) => {
  const detail = event.detail
  // Any push proves the server accepted and started the upload, which is what
  // lets handleUpload() tell a client timeout apart from a real failure.
  serverStarted.value = true
  uploadProgress.value = Math.floor(detail?.progress ?? 0)
}

const handleHfUploadComplete = (event: CustomEvent) => {
  finishSuccess(event.detail ?? {})
}

onMounted(() => {
  fetchWhoami()
  api.addEventListener('update_hf_upload_progress', updateHfProgress)
  // Emitted by py/upload_hf.py but never listened for before, so a successful
  // upload that outlived the HTTP request was never reported.
  api.addEventListener('hf_upload_complete', handleHfUploadComplete)
})

onUnmounted(() => {
  api.removeEventListener('update_hf_upload_progress', updateHfProgress)
  api.removeEventListener('hf_upload_complete', handleHfUploadComplete)
})
</script>
