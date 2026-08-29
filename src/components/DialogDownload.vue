<template>
  <div class="flex h-full flex-col gap-4">
    <div ref="container" class="whitespace-nowrap px-4">
      <div :class="['flex gap-4', $sm('justify-end')]">
        <Button
          :class="[$sm('w-auto', 'w-full')]"
          :label="$t('createDownloadTask')"
          @click="openCreateTask"
        ></Button>
        <Button
          :class="[$sm('w-auto', 'w-full')]"
          :label="$t('uploadFromLocalFile')"
          @click="openLocalUpload"
        ></Button>
      </div>
    </div>
    <div class="flex min-h-0 flex-1 flex-col gap-4">
      <div class="flex min-h-0 flex-1 flex-col gap-2">
        <div class="px-4 text-sm font-bold opacity-60">
          {{ $t('externalDownloads') }}
        </div>
        <ResponseScroll class="min-h-0 flex-1">
          <div class="w-full px-4">
            <ul class="m-0 flex list-none flex-col gap-4 p-0">
              <DownloadTaskItem
                v-for="item in remoteTasks"
                :key="item.taskId"
                :item="item"
              />
            </ul>
          </div>
        </ResponseScroll>
      </div>
      <div class="border-t border-gray-600"></div>
      <div class="flex min-h-0 flex-1 flex-col gap-2">
        <div class="px-4 text-sm font-bold opacity-60">
          {{ $t('localUploads') }}
        </div>
        <ResponseScroll class="min-h-0 flex-1">
          <div class="w-full px-4">
            <ul class="m-0 flex list-none flex-col gap-4 p-0">
              <DownloadTaskItem
                v-for="item in localTasks"
                :key="item.taskId"
                :item="item"
              />
            </ul>
          </div>
        </ResponseScroll>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import DialogCreateTask from 'components/DialogCreateTask.vue'
import DialogUpload from 'components/DialogUpload.vue'
import DownloadTaskItem from 'components/DownloadTaskItem.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { useContainerQueries } from 'hooks/container'
import { useDialog } from 'hooks/dialog'
import { useDownload } from 'hooks/download'
import { useModels } from 'hooks/model'
import { useToast } from 'hooks/toast'
import Button from 'primevue/button'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { data } = useDownload()
const models = useModels()
const { t } = useI18n()
const { toast } = useToast()
const dialog = useDialog()

const remoteTasks = computed(() =>
  data.value.filter((item) => item.source !== 'local'),
)
const localTasks = computed(() =>
  data.value.filter((item) => item.source === 'local'),
)

const openCreateTask = () => {
  dialog.open({
    key: `model-manager-create-task-${Date.now()}`,
    title: t('parseModelUrl'),
    content: DialogCreateTask,
  })
}

const refreshModelsAndConfig = async () => {
  await Promise.all([models.refresh(true)])
  toast.add({
    severity: 'success',
    summary: 'Refreshed Models',
    life: 2000,
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

const container = ref<HTMLElement | null>(null)

const { $sm } = useContainerQueries(container)
</script>
