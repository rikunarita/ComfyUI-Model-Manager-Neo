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
          <div v-show="hfUpload.active" class="w-full">
            <!--
              BUG FIX: the backend can only report 0% and then 100%
              (huggingface_hub exposes no per-chunk callback), so the bar sat at
              a motionless 0% for the whole transfer. Render it indeterminate
              until a real percentage arrives; `Progress` already supports the
              mode. The state lives in `hooks/hfUpload`, so the bar keeps
              showing (and re-appears on re-open) while the transfer runs.
            -->
            <Progress
              :model-value="hfUpload.progress"
              :mode="hfUpload.progress > 0 ? 'determinate' : 'indeterminate'"
            />
          </div>
          <div class="flex justify-between pt-6">
            <Button variant="secondary" @click="handleBackModelSelect">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
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
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Checkbox } from 'components/ui/checkbox'
import { Input } from 'components/ui/input'
import { Progress } from 'components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { configSetting } from 'hooks/config'
import { hfUploadState } from 'hooks/hfUpload'
import { useLoading } from 'hooks/loading'
import { genModelFullName, useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { app } from 'scripts/comfyAPI'
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

const handleUpload = async () => {
  if (!selectedModel.value) return
  hfUpload.taskId = null
  hfUpload.active = true
  hfUpload.progress = 0
  hfUpload.repoId = repoId.value ?? ''
  hfUpload.pathInRepo = pathInRepo.value ?? ''
  const payload = {
    type: selectedModel.value.type,
    pathIndex: selectedModel.value.pathIndex,
    fullname: genModelFullName(selectedModel.value),
    repoId: repoId.value,
    pathInRepo: pathInRepo.value,
    private: privateRepo.value,
  }
  try {
    const result = await request('/hf/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    // The transfer itself is tracked through the websocket events; the id
    // only lets this instance ignore events of an earlier upload.
    hfUpload.taskId = result?.taskId ?? null
  } catch (error) {
    // The server rejected the upload BEFORE it started (missing token,
    // invalid path, ...). A started transfer reports its own failure through
    // `hf_upload_error`.
    hfUpload.active = false
    hfUpload.taskId = null
    hfUpload.progress = 0
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: error instanceof Error ? error.message : String(error),
      life: 15000,
    })
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

onMounted(() => {
  fetchWhoami()
})
</script>
