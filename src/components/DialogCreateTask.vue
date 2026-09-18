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
import { computed, ref, watch } from 'vue'
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
import { type VersionModel, type WithResolved } from 'types/typings'
import { bytesToSize, isDirectFileUrl, previewUrlToFile } from 'utils/common'

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
