<template>
  <div class="flex h-full flex-col gap-4 px-5">
    <ResponseInput
      v-model="modelUrl"
      :allow-clear="true"
      update-trigger="input"
      :placeholder="$t('pleaseInputModelUrl')"
      @keydown.enter="searchModelsByUrl"
    >
      <template #suffix>
        <!--
          BUG FIX: was `<span class="pi pi-search text-base opacity-60">`.
          PrimeIcons is gone, so the span rendered empty — the button that
          starts the Civitai / Hugging Face / direct-link search was never drawn
          at all (only the Enter key still worked). Lucide `Search` restores it.
        -->
        <Search class="size-4 cursor-pointer opacity-60" @click="searchModelsByUrl" />
      </template>
    </ResponseInput>

    <!-- Direct file URL indicator with folder selection -->
    <div v-if="isDirectFile && modelUrl" class="flex flex-col gap-2">
      <div
        class="flex items-center gap-2 rounded-mm-ctl border border-mm-success/25 bg-mm-success/12 p-2 text-sm text-mm-success backdrop-blur-sm"
      >
        <!-- BUG FIX: `pi pi-check-circle` rendered empty (PrimeIcons removed). -->
        <CheckCircle class="size-4 shrink-0" />
        <span>Direct file download detected</span>
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
        <label class="text-sm font-medium">Subfolder (optional):</label>
        <ResponseInput
          v-model="customSubFolder"
          placeholder="e.g., subfolder/path"
          class="flex-1"
        />
      </div>
    </div>

    <div v-show="data.length > 0">
      <ResponseSelect v-model="current" :items="data" :type="isMobile ? 'drop' : 'button'">
        <template #prefix>
          <span>version:</span>
        </template>
      </ResponseSelect>
    </div>

    <ResponseScroll class="-mx-5 h-full">
      <div class="px-5">
        <KeepAlive>
          <ModelContent
            v-if="currentModel"
            :key="`${currentModel.id}-${currentModel.currentFileId}`"
            :model="currentModel"
            :editable="true"
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
            <div>No Models Found</div>
          </div>
        </div>
      </div>
    </ResponseScroll>
  </div>
</template>

<script setup lang="ts">
import { Box, CheckCircle, Download, Search } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import ModelContent from 'components/ModelContent.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import { useConfig } from 'hooks/config'
import { useDialog } from 'hooks/dialog'
import { useModelSearch } from 'hooks/download'
import { useLoading } from 'hooks/loading'
import { useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { type VersionModel, type WithResolved } from 'types/typings'
import { isDirectFileUrl, previewUrlToFile } from 'utils/common'

const { isMobile } = useConfig()
const { toast } = useToast()
const loading = useLoading()
const dialog = useDialog()

const modelUrl = ref<string>()

// Model type selection for direct downloads (REQUIRED, no default)
const selectedModelType = ref<string>()

// Custom subfolder input (NEW)
const customSubFolder = ref<string>('')

/** Pretty labels for the well-known folder keys; unknown keys render as-is. */
const MODEL_TYPE_LABELS: Record<string, string> = {
  checkpoints: 'Checkpoints',
  loras: 'LoRA',
  controlnet: 'ControlNet',
  vae: 'VAE',
  embeddings: 'Embeddings',
  upscale_models: 'Upscale Models',
  diffusers: 'Diffusers',
  clip: 'CLIP',
  clip_vision: 'CLIP Vision',
  diffusion_models: 'UNet/Diffusion Models',
  unet: 'UNet/Diffusion Models',
  style_models: 'Style Models',
  hypernetworks: 'Hypernetworks',
  gligen: 'GLIGEN',
  photomaker: 'PhotoMaker',
  vae_approx: 'VAE Approx',
  classifiers: 'Classifiers',
}

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
      label: MODEL_TYPE_LABELS[type] ?? type,
      value: type,
      command: () => {
        selectedModelType.value = type
      },
    }
  }),
)

const isDirectFile = computed(() => (modelUrl.value ? isDirectFileUrl(modelUrl.value) : false))

const { current, currentModel, data, search } = useModelSearch()
const { folders } = useModels()

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

const createDownTask = async (data: WithResolved<VersionModel>) => {
  // type が未選択の場合は送信を拒否
  if (!data.type) {
    toast.add({
      severity: 'warn',
      summary: 'Warning',
      detail: 'Please select model type first',
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

      // set preview file
      if (key === 'preview') {
        if (value) {
          const previewFile = await previewUrlToFile(value).catch(() => null)
          if (previewFile) {
            formData.append('previewFile', previewFile)
          } else {
            // BUG FIX: the browser-side preview fetch can fail (CORS, hotlink
            // protection, offline CDN, ...). Aborting the whole submission
            // made the Download click look completely dead - no dialog
            // change, no task. Hand the raw URL to the backend instead:
            // save_model_preview() downloads it server-side, where CORS does
            // not exist, and degrades to "no preview" if that fails too.
            toast.add({
              severity: 'warn',
              summary: 'Warning',
              detail:
                'Preview could not be fetched in the browser; the server will download it directly.',
              life: 5000,
            })
            formData.append('previewFile', value)
          }
        } else {
          // No preview: send an empty string (the backend's "nothing to do"
          // sentinel) instead of stringifying `undefined`.
          formData.append('previewFile', value ?? '')
        }
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
        summary: 'Error',
        detail: e.message ?? 'Failed to create download task',
        life: 15000,
      })
    })
    .finally(() => {
      loading.hide()
    })
}
</script>
