<template>
  <div class="h-full px-4">
    <Tabs v-model="stepValue" class="flex h-full flex-col">
      <TabsList class="grid w-full grid-cols-3">
        <TabsTrigger :value="1">{{ $t('selectModelType') }}</TabsTrigger>
        <TabsTrigger :value="2" :disabled="stepValue === 1">{{
          $t('selectSubdirectory')
        }}</TabsTrigger>
        <TabsTrigger :value="3" :disabled="stepValue === 1 || stepValue === 2">{{
          $t('chooseFile')
        }}</TabsTrigger>
      </TabsList>
      <TabsContent :value="1" class="flex-1 overflow-hidden">
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
      <TabsContent :value="2" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col overflow-hidden">
          <ResponseScroll class="flex-1">
            <Tree
              v-model="selectedFolder"
              :items="pathOptions"
              :get-key="(item: any) => item.key"
              :get-children="(item: any) => item.children"
              class="h-full"
            />
          </ResponseScroll>

          <div class="flex justify-between pt-6">
            <Button variant="secondary" @click="handleBackTypeSelect">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
            <Button :disabled="!enabledUpload" @click="handleConfirmSubdir">
              {{ $t('next') }}
              <ChevronRight class="size-4" />
            </Button>
          </div>
        </div>
      </TabsContent>
      <TabsContent :value="3" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col items-center justify-center">
          <!--
            The upload runs in the background and reports progress through the
            shared download-task system, so this dialog closes as soon as a file
            is picked. The accurate progress bar lives in the Download List.
          -->
          <div class="overflow-hidden py-8 wrap-break-word">
            <div class="overflow-hidden px-8">
              <div class="text-center">
                <div class="pb-2">
                  {{ $t('selectedSpecialPath') }}
                </div>
                <div class="leading-5 opacity-60">
                  {{ selectedModelFolder }}
                </div>
              </div>
            </div>
          </div>

          <div class="flex items-center justify-center gap-4">
            <Button
              v-for="item in uploadActions"
              :key="item.value"
              @click="item.command.call(item)"
            >
              {{ item.label }}
            </Button>
          </div>

          <div class="h-1/4"></div>
        </div>
      </TabsContent>
    </Tabs>
  </div>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import { computed, onMounted, ref, toValue } from 'vue'
import { useI18n } from 'vue-i18n'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { Tree } from 'components/ui/tree'
import { configSetting } from 'hooks/config'
import { useDialog } from 'hooks/dialog'
import { useModelFolder, useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { app } from 'scripts/comfyAPI'

const { t } = useI18n()
const { toast } = useToast()
const dialog = useDialog()

const stepValue = ref(1)

const { folders } = useModels()

const currentType = ref<string>()
const typeOptions = computed(() => {
  const excludeScanTypes = app.ui?.settings.getSettingValue<string>(configSetting.excludeScanTypes)
  const customBlackList =
    excludeScanTypes
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
          stepValue.value++
        },
      }
    })
})

const { pathOptions } = useModelFolder({ type: currentType })

const selectedModelFolder = ref<string>()
const selectedFolder = computed({
  get: () => (selectedModelFolder.value ? { key: selectedModelFolder.value } : undefined),
  set: (val: any) => {
    selectedModelFolder.value = val?.key
  },
})

const enabledUpload = computed(() => {
  return !!selectedModelFolder.value
})

const handleBackTypeSelect = () => {
  selectedModelFolder.value = undefined
  currentType.value = undefined
  stepValue.value--
}

const handleConfirmSubdir = () => {
  stepValue.value++
}

const supportedExtensions = ref<string[]>([])

// Beyond ComfyUI's model extensions (fetched from the backend) the picker also
// accepts common dataset/config/companion files so uploads are not limited to
// `.safetensors` (e.g. `.json`/`.jsonl` datasets, legacy `.bin`, archives).
const EXTRA_ACCEPT = [
  '.json',
  '.jsonl',
  '.txt',
  '.csv',
  '.tsv',
  '.yaml',
  '.yml',
  '.toml',
  '.npz',
  '.npy',
  '.onnx',
  '.pb',
  '.h5',
  '.tflite',
  '.gguf',
  '.pkl',
  '.pt',
  '.pth',
  '.bin',
  '.safetensors',
  '.ckpt',
  '.sft',
  '.zip',
]

const acceptAttr = computed(() => {
  const set = new Set<string>([...supportedExtensions.value, ...EXTRA_ACCEPT])
  return [...set].join(',')
})

const uploadActions = ref([
  {
    value: 'back',
    label: t('back'),
    command: () => {
      stepValue.value--
    },
  },
  {
    value: 'full',
    label: t('chooseFile'),
    command: () => {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = acceptAttr.value
      input.onchange = () => {
        const file = input.files?.item(0)
        if (!file) {
          return
        }

        const body = new FormData()
        body.append('folder', toValue(selectedModelFolder)!)
        // Send the total size up-front so the backend can report accurate
        // progress for the local task shown in the Download List.
        body.append('size', String(file.size))
        body.append('file', file)

        // Fire the upload and close immediately; progress + completion are
        // surfaced by the shared download-task system (Download List dialog).
        request('/upload', { method: 'POST', body }).catch(error => {
          toast.add({
            severity: 'error',
            summary: 'Error',
            detail: (error as Error).message,
            life: 5000,
          })
        })
        dialog.close()
      }
      input.click()
    },
  },
])

const fetchSupportedExtensions = async () => {
  try {
    const result = await request('/supported-extensions')
    supportedExtensions.value = result ?? []
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: (error as Error).message,
      life: 5000,
    })
  }
}

onMounted(() => {
  fetchSupportedExtensions()
})
</script>
