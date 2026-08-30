<template>
  <li class="rounded-lg border border-gray-500 p-4">
    <div class="flex gap-4 overflow-hidden whitespace-nowrap">
      <div class="h-18 preview-aspect">
        <div v-if="isVideoUrl(item.preview)" class="h-full w-full">
          <PreviewVideo :src="item.preview" />
        </div>
        <img v-else :src="item.preview" />
      </div>
      <div class="flex flex-1 flex-col gap-3 overflow-hidden">
        <div class="flex items-center gap-3 overflow-hidden">
          <span class="flex-1 overflow-hidden text-ellipsis">
            {{ item.fullname }}
          </span>
          <span v-show="item.status === 'waiting'" class="h-4">
            <i class="pi pi-spinner pi-spin"></i>
          </span>
          <span
            v-show="item.status === 'doing' && !isLocal"
            class="h-4 cursor-pointer"
            @click="item.pauseTask"
          >
            <i class="pi pi-pause-circle"></i>
          </span>
          <span
            v-show="item.status === 'pause' && !isLocal"
            class="h-4 cursor-pointer"
            @click="item.resumeTask"
          >
            <i class="pi pi-play-circle"></i>
          </span>
          <span class="h-4 cursor-pointer" @click="item.deleteTask">
            <i class="pi pi-trash text-red-400"></i>
          </span>
        </div>
        <div class="h-2 overflow-hidden rounded bg-gray-200">
          <div
            class="h-full bg-blue-500 transition-[width]"
            :class="{ 'animate-pulse': unknownTotal && item.status === 'doing' }"
            :style="{ width: `${barWidth}%` }"
          ></div>
        </div>
        <div class="flex justify-between">
          <div>{{ progressText }}</div>
          <div v-show="item.status === 'doing'">
            {{ item.downloadSpeed }}
          </div>
        </div>
      </div>
    </div>
  </li>
</template>

<script setup lang="ts">
import PreviewVideo from 'components/PreviewVideo.vue'
import { DownloadTask } from 'types/typings'
import { bytesToSize } from 'utils/common'
import { isVideoUrl } from 'utils/media'
import { computed } from 'vue'

const props = defineProps<{ item: DownloadTask }>()

const isLocal = computed(() => props.item.source === 'local')

const unknownTotal = computed(
  () => isLocal.value && (!props.item.totalSize || props.item.totalSize <= 0),
)

const barWidth = computed(() => {
  if (unknownTotal.value) {
    return props.item.status === 'doing' ? 100 : 0
  }
  return props.item.progress
})

const progressText = computed(() => {
  if (unknownTotal.value) {
    return bytesToSize(props.item.downloadedSize)
  }
  return props.item.downloadProgress
})
</script>
