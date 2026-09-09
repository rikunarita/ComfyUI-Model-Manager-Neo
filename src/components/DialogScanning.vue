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
            <Button :disabled="!enabledScan" @click="handleConfirmSubdir">
              {{ $t('next') }}
              <ChevronRight class="size-4" />
            </Button>
          </div>
        </div>
      </TabsContent>
      <TabsContent value="3" class="flex-1 overflow-hidden">
        <div class="overflow-hidden py-8 wrap-break-word">
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
          <div v-if="scanProgress > -1">
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
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Progress } from 'components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { Tree } from 'components/ui/tree'
import { configSetting } from 'hooks/config'
import { useModelFolder, useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useScan } from 'hooks/scan'
import { useToast } from 'hooks/toast'
import { app } from 'scripts/comfyAPI'

const { t } = useI18n()
const { toast } = useToast()

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

// Scan progress lives in an app-lifetime store so updates are never missed
// while this dialog is closed (see hooks/scan.ts).
const { scanModels, scanning, updates, syncFromServer, beginScan } = useScan()

const batchScanningStep = ref(0)
const scanTotalCount = computed(() => {
  return Object.keys(scanModels.value).length
})
const scanCompleteCount = computed(() => {
  return Object.keys(scanModels.value).filter(key => scanModels.value[key]).length
})
const scanProgress = computed(() => {
  if (scanTotalCount.value === 0) {
    return -1
  }
  const progress = scanCompleteCount.value / scanTotalCount.value
  return Number(progress.toFixed(4)) * 100
})

/**
 * BUG FIX — this is why "batch scan results were never displayed".
 *
 * The progress step (2) used to be reachable ONLY through a successful
 * `POST /model-info/scan` response. That request cannot answer until the
 * server has walked the entire model library (`create_scan_model_info_task`
 * runs `os.walk` over every registered model folder before it replies), and
 * ComfyUI's `api.fetchApi` aborts any request whose response headers have not
 * arrived within 60 seconds (`FETCH_RESPONSE_HEADERS_TIMEOUT_MS = 60_000` in
 * ComfyUI_frontend `src/scripts/api.ts`). On a large library — many files,
 * slow/networked disk, antivirus, symlinked trees walked with
 * `followlinks=True`, or the same base path registered by several model types
 * — the walk exceeds that budget and the promise rejects.
 *
 * The rejection does NOT stop the server: aiohttp does not cancel the handler
 * when the client disconnects, so the task file is still written and the scan
 * still runs to completion, logging "Send update scan information task to
 * frontend." and "Completed scan model information.". The websocket pushes
 * were received by the scan store, but `catch { batchScanningStep.value = 1 }`
 * had already parked the dialog on the type-selection step and nothing ever
 * moved it forward again — so every result was silently discarded.
 *
 * The dialog now follows the *store* (the authoritative live state fed by the
 * websocket pushes and by `syncFromServer`) instead of the round-trip, so a
 * scan that starts, resumes or completes by any route is always displayed.
 * `updates` is watched as well as `scanning` because a push that arrives while
 * `scanning` is already true would not otherwise re-trigger the transition.
 */
watch([scanning, updates], ([running]) => {
  if (running && batchScanningStep.value !== 2) {
    batchScanningStep.value = 2
  }
})

const handleScanModelInformation = async (item: { value: string }) => {
  batchScanningStep.value = 0
  const mode = item.value
  const path = selectedModelFolder.value
  const updatesBefore = updates.value

  try {
    const result = await request('/model-info/scan', {
      method: 'POST',
      body: JSON.stringify({ mode, path }),
    })
    // BUG FIX: the server starts scanning before this response is delivered, so
    // websocket progress pushes can overtake it. Applying the (older) response
    // body then rewound a partly finished scan back to 0%. Keep the live state
    // whenever a push already arrived, otherwise seed from the response.
    beginScan(updates.value === updatesBefore ? (result?.models ?? {}) : undefined)
    batchScanningStep.value = 2
  } catch (error) {
    // A rejected POST does not mean "no scan": the server keeps working after
    // the client gives up (see the note above). Reconcile with the server
    // before falling back, and never fail silently — the old bare
    // `catch { batchScanningStep.value = 1 }` told the user nothing at all.
    if (updates.value !== updatesBefore) {
      batchScanningStep.value = 2
      return
    }
    const live = await syncFromServer()
    if (scanning.value || live) {
      batchScanningStep.value = 2
      return
    }
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: error instanceof Error ? error.message : String(error),
      life: 15000,
    })
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
  const listContent = await syncFromServer()
  // A scan is in flight (started from this dialog or resumed by the server):
  // stay on the progress step. Deriving the step from `listContent` alone let a
  // stale mount-time GET throw the dialog back to the type-selection step while
  // the scan was still running, hiding every subsequent progress update.
  if (scanning.value) {
    batchScanningStep.value = 2
    return
  }
  batchScanningStep.value = listContent && Object.keys(listContent).length ? 2 : 1
}

onMounted(() => {
  refreshTaskContent()
})
</script>
