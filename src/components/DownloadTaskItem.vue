<template>
  <li class="rounded-mm-card border border-mm-border p-4 mm-transition hover:shadow-mm-1">
    <div class="flex gap-4 overflow-hidden whitespace-nowrap">
      <div class="h-18 preview-aspect">
        <div v-if="isVideoUrl(item.preview)" class="h-full w-full">
          <PreviewVideo :src="item.preview" />
        </div>
        <img v-else :src="item.preview" class="h-full w-full object-cover rounded-mm-ctl" />
      </div>
      <div class="flex flex-1 flex-col gap-3 overflow-hidden">
        <div class="flex items-center gap-3 overflow-hidden">
          <span class="flex-1 overflow-hidden text-ellipsis text-mm-fg">
            {{ item.fullname }}
          </span>
          <span v-show="item.status === 'waiting'" class="h-4">
            <Loader2 class="size-4 animate-spin text-mm-muted-fg" />
          </span>
          <button
            v-show="item.status === 'doing' && !isLocal"
            class="h-4 cursor-pointer mm-transition hover:scale-110"
            @click="item.pauseTask"
          >
            <PauseCircle class="size-4 text-mm-muted-fg hover:text-mm-fg" />
          </button>
          <button
            v-show="item.status === 'pause' && !isLocal"
            class="h-4 cursor-pointer mm-transition hover:scale-110"
            @click="item.resumeTask"
          >
            <PlayCircle class="size-4 text-mm-muted-fg hover:text-mm-fg" />
          </button>
          <button class="h-4 cursor-pointer mm-transition hover:scale-110" @click="item.deleteTask">
            <Trash2 class="size-4 text-mm-danger hover:brightness-110" />
          </button>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-mm-surface">
          <div
            class="h-full rounded-full bg-mm-accent mm-transition"
            :class="{ 'animate-pulse': isLocal && item.status === 'doing' }"
            :style="{ width: `${barWidth}%` }"
          ></div>
        </div>
        <div class="flex justify-between text-xs text-mm-muted-fg">
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
import { Loader2, PauseCircle, PlayCircle, Trash2 } from '@lucide/vue'
import PreviewVideo from 'components/PreviewVideo.vue'
import type { DownloadTask } from 'types/typings'
import { bytesToSize } from 'utils/common'
import { isVideoUrl } from 'utils/media'
import { computed } from 'vue'

const props = defineProps<{ item: DownloadTask }>()

const isLocal = computed(() => props.item.source === 'local')

const barWidth = computed(() => {
  if (isLocal.value) {
    return props.item.status === 'doing' ? 100 : props.item.progress
  }
  return props.item.progress
})

const progressText = computed(() => {
  if (isLocal.value) {
    return bytesToSize(props.item.downloadedSize)
  }
  return props.item.downloadProgress
})
</script>
