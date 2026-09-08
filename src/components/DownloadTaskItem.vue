<template>
  <li class="mm-transition rounded-mm-card border border-mm-border p-4 hover:shadow-mm-1">
    <div class="flex gap-4 overflow-hidden whitespace-nowrap">
      <div class="preview-aspect h-18">
        <div v-if="isVideoUrl(item.preview)" class="size-full">
          <PreviewVideo :src="item.preview" />
        </div>
        <img v-else :src="item.preview" class="size-full rounded-mm-ctl object-cover" />
      </div>
      <div class="flex flex-1 flex-col gap-3 overflow-hidden">
        <div class="flex items-center gap-3 overflow-hidden">
          <span class="flex-1 overflow-hidden text-ellipsis text-mm-fg">
            {{ item.fullname }}
          </span>
          <span v-show="item.status === 'waiting'" class="h-6">
            <Loader2 class="size-5 animate-spin text-mm-muted-fg" />
          </span>
          <button
            v-show="item.status === 'doing' && !isLocal"
            class="mm-transition h-6 cursor-pointer border-0 bg-transparent p-0 hover:scale-110"
            @click="item.pauseTask"
          >
            <PauseCircle class="size-5 text-mm-muted-fg hover:text-mm-fg" />
          </button>
          <button
            v-show="item.status === 'pause' && !isLocal"
            class="mm-transition h-6 cursor-pointer border-0 bg-transparent p-0 hover:scale-110"
            @click="item.resumeTask"
          >
            <PlayCircle class="size-5 text-mm-muted-fg hover:text-mm-fg" />
          </button>
          <button
            class="mm-transition h-6 cursor-pointer border-0 bg-transparent p-0 hover:scale-110"
            @click="item.deleteTask"
          >
            <Trash2 class="size-5 text-mm-danger hover:brightness-110" />
          </button>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-mm-surface">
          <div
            class="mm-transition h-full rounded-full bg-mm-accent"
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
import { computed } from 'vue'
import PreviewVideo from 'components/PreviewVideo.vue'
import { type DownloadTask } from 'types/typings'
import { isVideoUrl } from 'utils/media'

const props = defineProps<{ item: DownloadTask }>()

const isLocal = computed(() => props.item.source === 'local')

// The backend is now given the real file size for local uploads and reports an
// accurate percentage, so local and remote tasks share the same progress fields
// (previously local uploads were pinned to a fake 100% while "doing").
const barWidth = computed(() => props.item.progress)

const progressText = computed(() => props.item.downloadProgress)
</script>
