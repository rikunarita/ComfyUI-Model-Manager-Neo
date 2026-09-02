<template>
  <div
    class="group relative flex flex-col overflow-hidden rounded-mm-card border border-mm-border bg-mm-surface mm-transition hover:-translate-y-0.5 hover:shadow-mm-2 hover:border-mm-accent/30"
    @click="handleClick"
  >
    <!-- Preview area with gradient scrim -->
    <div class="preview-aspect relative overflow-hidden">
      <div v-if="isVideoUrl(model.preview)" class="h-full w-full">
        <PreviewVideo :src="model.preview" />
      </div>
      <img v-else :src="model.preview" class="h-full w-full object-cover" />
      
      <!-- Gradient scrim for name readability -->
      <div class="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/60 to-transparent"></div>
      
      <!-- Badges (type/size) -->
      <div class="absolute right-2 top-2 flex flex-col gap-1">
        <Badge variant="default" class="backdrop-blur-sm">
          {{ model.type }}
        </Badge>
        <Badge v-if="model.sizeBytes" variant="secondary" class="backdrop-blur-sm">
          {{ bytesToSize(model.sizeBytes) }}
        </Badge>
      </div>

      <!-- Hover actions (revealed on hover) -->
      <div class="absolute right-2 top-1/2 flex -translate-y-1/2 flex-col gap-1 opacity-0 mm-transition group-hover:opacity-100 group-hover:translate-x-0 translate-x-1">
        <Button
          v-for="action in actions"
          :key="action.key"
          variant="secondary"
          size="icon-xs"
          class="backdrop-blur-sm bg-mm-bg/80 hover:bg-mm-surface-hover"
          @click.stop="action.command?.()"
        >
          <component :is="action.icon" class="size-3" />
        </Button>
      </div>
    </div>

    <!-- Name overlay -->
    <div class="absolute inset-x-0 bottom-0 p-2">
      <div class="text-shadow text-sm font-medium text-white line-clamp-2">
        {{ model.shortname || model.basename }}
      </div>
    </div>

    <!-- Selection ring -->
    <div
      v-if="isSelected"
      class="pointer-events-none absolute inset-0 rounded-mm-card ring-2 ring-mm-accent/60"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Copy, Workflow } from '@lucide/vue'
import { Badge } from 'components/ui/badge'
import { Button } from 'components/ui/button'
import PreviewVideo from 'components/PreviewVideo.vue'
import type { VersionModel } from 'types/typings'
import { bytesToSize } from 'utils/common'
import { isVideoUrl } from 'utils/media'
import { computed } from 'vue'

interface Props {
  model: VersionModel
  isSelected?: boolean
  actions?: Array<{ key: string; icon: any; command?: () => void }>
}

const props = withDefaults(defineProps<Props>(), {
  actions: () => [
    { key: 'add', icon: Plus, command: () => {} },
    { key: 'copy', icon: Copy, command: () => {} },
    { key: 'workflow', icon: Workflow, command: () => {} },
  ],
})

const emit = defineEmits<{
  click: [model: VersionModel]
}>()

const handleClick = () => {
  emit('click', props.model)
}
</script>
