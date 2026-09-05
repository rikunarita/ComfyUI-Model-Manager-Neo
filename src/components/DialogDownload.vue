<template>
  <div class="h-full px-4">
    <div class="flex justify-end gap-2 py-4">
      <Button @click="openCreateDownload">
        <Plus class="size-4" />
        {{ $t('createDownloadTask') }}
      </Button>
      <Button @click="openLocalUpload">
        <Upload class="size-4" />
        {{ $t('uploadFromLocalFile') }}
      </Button>
    </div>

    <div class="flex h-full flex-col gap-4 overflow-hidden">
      <div v-if="externalDownloads.length > 0" class="flex flex-col gap-2">
        <div class="text-sm font-medium text-mm-muted-fg">
          {{ $t('externalDownloads') }}
        </div>
        <div class="flex flex-col gap-2">
          <DownloadTaskItem
            v-for="item in externalDownloads"
            :key="item.taskId"
            :item="item"
          />
        </div>
      </div>

      <div v-if="localUploads.length > 0" class="flex flex-col gap-2">
        <div class="text-sm font-medium text-mm-muted-fg">
          {{ $t('localUploads') }}
        </div>
        <div class="flex flex-col gap-2">
          <DownloadTaskItem
            v-for="item in localUploads"
            :key="item.taskId"
            :item="item"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Upload } from '@lucide/vue'
import DownloadTaskItem from 'components/DownloadTaskItem.vue'
import { Button } from 'components/ui/button'
import { useDialog } from 'hooks/dialog'
import { useDownload } from 'hooks/download'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const dialog = useDialog()
const { data } = useDownload()

const externalDownloads = computed(() => {
  return data.value.filter((item) => item.source !== 'local')
})

const localUploads = computed(() => {
  return data.value.filter((item) => item.source === 'local')
})

const openCreateDownload = () => {
  dialog.open({
    key: 'model-manager-create-download',
    title: t('createDownloadTask'),
    content: DialogCreateTask,
  })
}

const openLocalUpload = () => {
  dialog.open({
    key: 'model-manager-upload',
    title: t('uploadModel'),
    content: DialogUpload,
    headerButtons: [
      {
        key: 'refresh',
        icon: 'pi pi-refresh',
        command: refreshModelsAndConfig,
      },
    ],
  })
}
</script>
