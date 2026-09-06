<template>
  <div class="h-full px-4">
    <div v-show="batchScanningStep === 0" class="h-full">
      <div class="flex h-full items-center px-8">
        <div class="h-20 w-full opacity-60">
          <Progress mode="indeterminate" style="height: 6px"></Progress>
        </div>
      </div>
    </div>

    <Tabs v-show="batchScanningStep === 1" v-model="stepValue" class="flex h-full flex-col">
      <TabsList class="grid w-full grid-cols-3">
        <TabsTrigger value="1">{{ $t('selectModelType') }}</TabsTrigger>
        <TabsTrigger value="2" :disabled="stepValue === '1'">{{
          $t('selectSubdirectory')
        }}</TabsTrigger>
        <TabsTrigger value="3" :disabled="stepValue === '1' || stepValue === '2'">{{
          $t('scanModelInformation')
        }}</TabsTrigger>
      </TabsList>
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
      <TabsContent value="2" class="flex-1 overflow-hidden">
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
            <Button :disabled="!enabledScan" @click="handleConfirmSubdir">
              {{ $t('next') }}
              <ChevronRight class="size-4" />
            </Button>
          </div>
        </div>
      </TabsContent>
      <TabsContent value="3" class="flex-1 overflow-hidden">
        <div class="overflow-hidden break-words py-8">
          <div class="overflow-hidden px-8">
            <div v-show="currentType === allType" class="text-center">
              {{ $t('selectedAllPaths') }}
            </div>
            <div v-show="currentType !== allType" class="text-center">
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
          <Button v-for="item in scanActions" :key="item.value" @click="() => item.command(item)">
            {{ item.label }}
          </Button>
        </div>
      </TabsContent>
    </Tabs>

    <div v-show="batchScanningStep === 2" class="h-full">
      <div class="flex h-full items-center px-8">
        <div class="h-20 w-full">
          <div v-show="scanProgress > -1">
            <Progress :model-value="scanProgress">
              {{ scanCompleteCount }}
              / {{ scanTotalCount }}
            </Progress>
          </div>

          <div v-show="scanProgress === -1" class="text-center">
            <Button variant="secondary" @click="handleBackTypeSelect">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
            <span class="pl-2">{{ $t('noModelsInCurrentPath') }}</span>
          </div>
        </div>
      </div>
    </div>
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
import { api, app } from 'scripts/comfyAPI'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const stepValue = ref('1')

const { folders } = useModels()

const allType = 'All'
const currentType = ref<string>()
const typeOptions = computed(() => {
  const excludeScanTypes = app.ui?.settings.getSettingValue<string>(configSetting.excludeScanTypes)
  const customBlackList =
    excludeScanTypes
      ?.split(',')
      .map((type: string) => type.trim())
      .filter(Boolean) ?? []
  return [
    allType,
    ...Object.keys(folders.value).filter(folder => !customBlackList.includes(folder)),
  ].map(type => {
    return {
      label: type,
      value: type,
      command: () => {
        currentType.value = type
        stepValue.value = currentType.value === allType ? '3' : '2'
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

const enabledScan = computed(() => {
  return currentType.value === allType || !!selectedModelFolder.value
})

const handleBackTypeSelect = () => {
  selectedModelFolder.value = undefined
  currentType.value = undefined
  stepValue.value = '1'
  batchScanningStep.value = 1
}

const handleConfirmSubdir = () => {
  stepValue.value = '3'
}

const batchScanningStep = ref(0)
const scanModelsList = ref<Record<string, boolean>>({})
const scanTotalCount = computed(() => {
  return Object.keys(scanModelsList.value).length
})
const scanCompleteCount = computed(() => {
  return Object.keys(scanModelsList.value).filter(key => scanModelsList.value[key]).length
})
const scanProgress = computed(() => {
  if (scanTotalCount.value === 0) {
    return -1
  }
  const progress = scanCompleteCount.value / scanTotalCount.value
  return Number(progress.toFixed(4)) * 100
})

const handleScanModelInformation = async (item: { value: string }) => {
  batchScanningStep.value = 0
  const mode = item.value
  const path = selectedModelFolder.value

  try {
    const result = await request('/model-info/scan', {
      method: 'POST',
      body: JSON.stringify({ mode, path }),
    })
    scanModelsList.value = result?.models ?? {}
    batchScanningStep.value = 2
  } catch {
    batchScanningStep.value = 1
  }
}

const scanActions = ref([
  {
    value: 'back',
    label: t('back'),
    command: () => {
      stepValue.value = currentType.value === allType ? '1' : '2'
    },
  },
  {
    value: 'full',
    label: t('scanFullInformation'),
    command: handleScanModelInformation,
  },
  {
    value: 'diff',
    label: t('scanMissInformation'),
    command: handleScanModelInformation,
  },
])

const refreshTaskContent = async () => {
  const result = await request('/model-info/scan')
  const listContent = result?.models ?? {}
  scanModelsList.value = listContent
  batchScanningStep.value = Object.keys(listContent).length ? 2 : 1
}

onMounted(() => {
  refreshTaskContent()

  api.addEventListener('update_scan_information_task', (event: CustomEvent) => {
    const content = event.detail
    scanModelsList.value = content.models
  })
})
</script>
