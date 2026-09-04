<template>
  <div class="h-full px-4">
    <Tabs v-model="stepValue" class="flex h-full flex-col">
      <TabsList class="grid w-full grid-cols-3">
        <TabsTrigger :value="1">{{ $t('selectModelType') }}</TabsTrigger>
        <TabsTrigger :value="2" :disabled="stepValue === 1">{{ $t('selectSubdirectory') }}</TabsTrigger>
        <TabsTrigger :value="3" :disabled="stepValue === 1 || stepValue === 2">{{ $t('chooseFile') }}</TabsTrigger>
      </TabsList>
      <TabsContent :value="1" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col overflow-hidden">
          <ResponseScroll>
            <div class="flex flex-wrap gap-4">
              <Button
                v-for="item in typeOptions"
                :key="item.value"
                @click="item.command"
              >
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
              :items="pathOptions"
              :get-key="(item: any) => item.key"
              :get-children="(item: any) => item.children"
              v-model="selectedFolder"
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
          <template v-if="showUploadProgress">
            <div class="w-4/5">
              <Progress :model-value="uploadProgress" />
            </div>
          </template>

          <template v-else>
            <div class="overflow-hidden break-words py-8">
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
          </template>

          <div class="h-1/4"></div>
        </div>
      </TabsContent>
    </Tabs>
  </div>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Progress } from 'components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { Tree } from 'components/ui/tree'
import { configSetting } from 'hooks/config'
import { useModelFolder, useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { api, app } from 'scripts/comfyAPI'
import { computed, onMounted, onUnmounted, ref, toValue } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const { toast } = useToast()

const stepValue = ref(1)

const { folders } = useModels()

const currentType = ref<string>()
const typeOptions = computed(() => {
  const excludeScanTypes = app.ui?.settings.getSettingValue<string>(
    configSetting.excludeScanTypes,
  )
  const customBlackList =
    excludeScanTypes
      ?.split(',')
      .map((type: string) => type.trim())
      .filter(Boolean) ?? []
  return Object.keys(folders.value)
    .filter((folder) => !customBlackList.includes(folder))
    .map((type) => {
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
  get: () => selectedModelFolder.value ? { key: selectedModelFolder.value } : undefined,
  set: (val: any) => { selectedModelFolder.value = val?.key },
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

const uploadTotalSize = ref<number>()
const uploadSize = ref<number>()
const uploadProgress = computed(() => {
  const total = toValue(uploadTotalSize)
  const size = toValue(uploadSize)
  if (typeof total === 'number' && typeof size === 'number') {
    return Math.floor((size / total) * 100)
  }
  return undefined
})
const showUploadProgress = computed(() => {
  return typeof uploadProgress.value !== 'undefined'
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
      input.accept = supportedExtensions.value.join(',')
      input.onchange = async () => {
        const files = input.files
        const file = files?.item(0)
        if (!file) {
          return
        }

        try {
          uploadTotalSize.value = file.size
          uploadSize.value = 0
          const body = new FormData()
          body.append('folder', toValue(selectedModelFolder)!)
          body.append('file', file)

          await request('/upload', {
            method: 'POST',
            body: body,
          })
        } catch (error) {
          toast.add({
            severity: 'error',
            summary: 'Error',
            detail: (error as Error).message,
            life: 5000,
          })
        }
      }
      input.click()
    },
  },
])

const supportedExtensions = ref<string[]>([])

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

const update_process = (event: CustomEvent) => {
  const detail = event.detail
  uploadSize.value = detail.uploaded_size
}

onMounted(() => {
  fetchSupportedExtensions()

  api.addEventListener('update_upload_progress', update_process)
})

onUnmounted(() => {
  api.removeEventListener('update_upload_progress', update_process)
})
</script>
