<script setup lang="ts">
import { BrushCleaning, Pencil, RefreshCw, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Checkbox } from 'components/ui/checkbox'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { useModels } from 'hooks/model'
import { useModelDetail } from 'hooks/modelDetail'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { bytesToSize } from 'utils/common'
import { NO_PREVIEW_URL } from 'utils/media'
import { genModelKey } from 'utils/model'

/**
 * Local hygiene scan (no hashing, no network): orphaned sidecar files
 * (previews / notes without their model), models without any preview, and
 * empty folders. Cleanup reuses the existing DELETE route per item.
 */
interface HygieneItem {
  type: string
  pathIndex: number
  fullname: string
  sizeBytes: number
}

const { t } = useI18n()
const { toast, confirm } = useToast()
const { data, refreshFolder, getFullPath } = useModels()
const { openModelDetail } = useModelDetail()

const orphans = ref<HygieneItem[]>([])
const emptyFolders = ref<HygieneItem[]>([])
const scanning = ref(false)

const scan = async () => {
  scanning.value = true
  try {
    const result = (await request('/hygiene')) as {
      orphans: HygieneItem[]
      empty: HygieneItem[]
    }
    orphans.value = result?.orphans ?? []
    emptyFolders.value = result?.empty ?? []
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: (error as Error).message,
      life: 8000,
    })
  } finally {
    scanning.value = false
  }
}
onMounted(scan)

/** Models without any preview file, straight from the cached listings. */
const missingPreview = computed(() => {
  const out: (HygieneItem & { key: string })[] = []
  for (const [type, list] of Object.entries(data.value)) {
    for (const m of list) {
      if (m.isFolder || m.preview !== NO_PREVIEW_URL) continue
      out.push({
        type,
        pathIndex: m.pathIndex,
        fullname: `${m.subFolder ? `${m.subFolder}/` : ''}${m.basename}${m.extension}`,
        sizeBytes: m.sizeBytes || 0,
        key: genModelKey(m),
      })
    }
  }
  return out
})

const selectedOrphans = ref<Record<string, boolean>>({})
const selectedEmpty = ref<Record<string, boolean>>({})
const keyOf = (item: HygieneItem) => `${item.type}:${item.pathIndex}:${item.fullname}`

const selectedCount = computed(
  () =>
    Object.values(selectedOrphans.value).filter(Boolean).length +
    Object.values(selectedEmpty.value).filter(Boolean).length,
)

const deleteSelected = () => {
  const orphanItems = orphans.value.filter(i => selectedOrphans.value[keyOf(i)])
  const emptyItems = emptyFolders.value.filter(i => selectedEmpty.value[keyOf(i)])
  if (!orphanItems.length && !emptyItems.length) return
  confirm.require({
    message: t('deleteAsk', [`${t('hygiene')} (${orphanItems.length + emptyItems.length})`]),
    header: 'Danger',
    icon: 'pi pi-info-circle',
    rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
    acceptProps: { label: t('delete'), severity: 'danger' },
    accept: async () => {
      const touched = new Set<string>()
      for (const item of [...orphanItems, ...emptyItems]) {
        touched.add(item.type)
        try {
          await request(`/model/${item.type}/${item.pathIndex}/${item.fullname}`, {
            method: 'DELETE',
          })
        } catch (error) {
          toast.add({
            severity: 'warn',
            summary: t('error'),
            detail: (error as Error).message,
            life: 6000,
          })
        }
      }
      selectedOrphans.value = {}
      selectedEmpty.value = {}
      for (const type of touched) refreshFolder(type).catch(() => {})
      await scan()
    },
    reject: () => {},
  })
}

const openEdit = (item: HygieneItem) => {
  for (const m of data.value[item.type] ?? []) {
    if (
      !m.isFolder &&
      `${m.subFolder ? `${m.subFolder}/` : ''}${m.basename}${m.extension}` === item.fullname &&
      m.pathIndex === item.pathIndex
    ) {
      openModelDetail(m)
      return
    }
  }
}

const pathOf = (item: HygieneItem) => {
  const folders = getFullPath({
    type: item.type,
    pathIndex: item.pathIndex,
    subFolder: '',
    basename: item.fullname,
    extension: '',
  } as any)
  return folders
}
</script>

<template>
  <div class="flex h-full flex-col gap-4 px-5 pb-5">
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 text-sm text-mm-muted-fg">
        <BrushCleaning class="size-4" />
        <span>{{ $t('hygieneHint') }}</span>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="secondary" size="sm" :disabled="scanning" @click="scan">
          <RefreshCw class="size-4" :class="scanning && 'animate-spin'" />
          {{ $t('refresh') }}
        </Button>
        <Button
          variant="destructive"
          size="sm"
          :disabled="selectedCount === 0"
          @click="deleteSelected"
        >
          <Trash2 class="size-4" />
          {{ $t('delete') }} ({{ selectedCount }})
        </Button>
      </div>
    </div>

    <Tabs default-value="orphans" class="flex min-h-0 flex-1 flex-col">
      <TabsList class="grid w-full grid-cols-3">
        <TabsTrigger value="orphans">{{ $t('hygieneOrphans') }} ({{ orphans.length }})</TabsTrigger>
        <TabsTrigger value="missing"
          >{{ $t('hygieneMissingPreview') }} ({{ missingPreview.length }})</TabsTrigger
        >
        <TabsTrigger value="empty"
          >{{ $t('hygieneEmptyFolders') }} ({{ emptyFolders.length }})</TabsTrigger
        >
      </TabsList>

      <TabsContent value="orphans" class="min-h-0 flex-1 overflow-hidden">
        <ResponseScroll>
          <div class="flex flex-col gap-1 py-2">
            <div
              v-for="item in orphans"
              :key="keyOf(item)"
              class="flex items-center gap-2 rounded-mm-ctl border border-mm-border px-2 py-1 text-sm"
            >
              <Checkbox v-model="selectedOrphans[keyOf(item)]" />
              <span class="flex-1 truncate" :title="pathOf(item)">{{ pathOf(item) }}</span>
              <span class="shrink-0 text-xs text-mm-muted-fg">{{
                bytesToSize(item.sizeBytes)
              }}</span>
            </div>
            <div v-if="!orphans.length" class="py-8 text-center text-sm text-mm-muted-fg">
              {{ $t('hygieneClean') }}
            </div>
          </div>
        </ResponseScroll>
      </TabsContent>

      <TabsContent value="missing" class="min-h-0 flex-1 overflow-hidden">
        <ResponseScroll>
          <div class="flex flex-col gap-1 py-2">
            <div
              v-for="item in missingPreview"
              :key="item.key"
              class="flex items-center gap-2 rounded-mm-ctl border border-mm-border px-2 py-1 text-sm"
            >
              <span class="flex-1 truncate" :title="pathOf(item)">{{ pathOf(item) }}</span>
              <Button
                variant="ghost"
                size="icon-sm"
                :title="$t('editModel')"
                @click="openEdit(item)"
              >
                <Pencil class="size-4" />
              </Button>
            </div>
            <div v-if="!missingPreview.length" class="py-8 text-center text-sm text-mm-muted-fg">
              {{ $t('hygieneClean') }}
            </div>
          </div>
        </ResponseScroll>
      </TabsContent>

      <TabsContent value="empty" class="min-h-0 flex-1 overflow-hidden">
        <ResponseScroll>
          <div class="flex flex-col gap-1 py-2">
            <div
              v-for="item in emptyFolders"
              :key="keyOf(item)"
              class="flex items-center gap-2 rounded-mm-ctl border border-mm-border px-2 py-1 text-sm"
            >
              <Checkbox v-model="selectedEmpty[keyOf(item)]" />
              <span class="flex-1 truncate" :title="pathOf(item)">{{ pathOf(item) }}</span>
            </div>
            <div v-if="!emptyFolders.length" class="py-8 text-center text-sm text-mm-muted-fg">
              {{ $t('hygieneClean') }}
            </div>
          </div>
        </ResponseScroll>
      </TabsContent>
    </Tabs>
  </div>
</template>
