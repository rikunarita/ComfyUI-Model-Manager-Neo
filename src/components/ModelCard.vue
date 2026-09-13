<template>
  <div
    ref="container"
    class="mm-transition relative h-full rounded-mm-card select-none hover:-translate-y-0.5 hover:bg-mm-fg/6 hover:shadow-mm-2"
    @mouseenter="folderIcon?.enter()"
    @mouseleave="folderIcon?.leave()"
  >
    <div data-card-main class="flex size-full flex-col">
      <div data-card-preview class="flex-1 overflow-hidden">
        <div v-if="model.isFolder" class="size-full p-1">
          <FolderIcon ref="folderIcon" />
        </div>
        <div v-else-if="isVideoUrl(preview)" class="size-full p-1 hover:p-0">
          <PreviewVideo :src="preview" />
        </div>
        <div v-else class="size-full p-1 hover:p-0">
          <img class="size-full rounded-mm-ctl object-cover" :src="preview" />
        </div>
      </div>

      <slot name="name">
        <div class="flex justify-center overflow-hidden px-1">
          <span class="truncate">
            {{ model.basename }}
          </span>
        </div>
      </slot>
    </div>

    <div
      v-if="!model.isFolder"
      data-draggable-overlay
      class="absolute top-0 left-0 size-full"
      draggable="true"
      @dragend.stop="dragToAddModelNode(model, $event)"
    ></div>

    <!-- Glassmorphism badges (right-top) -->
    <div
      v-if="!model.isFolder"
      class="pointer-events-none absolute top-2 right-2 flex flex-col items-end gap-1"
      :style="{
        transform: `scale(${badgeScale})`,
        transformOrigin: 'right top',
      }"
    >
      <div
        class="rounded-full border border-white/20 bg-mm-accent/30 px-2.5 py-0.5 text-xs text-white backdrop-blur-md"
      >
        {{ model.type }}
      </div>
      <div
        v-if="model.sizeBytes"
        class="rounded-full border border-white/10 bg-black/40 px-2.5 py-0.5 text-xs text-white backdrop-blur-md"
      >
        {{ bytesToSize(model.sizeBytes) }}
      </div>
    </div>

    <slot name="extra"></slot>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import FolderIcon from 'components/FolderIcon.vue'
import PreviewVideo from 'components/PreviewVideo.vue'
import { useModelNodeAction } from 'hooks/model'
import { type BaseModel } from 'types/typings'
import { bytesToSize } from 'utils/common'
import { isVideoUrl } from 'utils/media'

interface Props {
  model: BaseModel
  /**
   * Card width in px, supplied by the grid that owns the layout.
   *
   * Optimization B-1: the badge scale used to come from a per-card
   * `useElementSize`, i.e. one ResizeObserver (and one reactive width) per
   * rendered card. The width is already known to the parent grid - passing it
   * down makes the scale a pure computation and removes every observer.
   */
  width?: number
}

const props = withDefaults(defineProps<Props>(), { width: 200 })

const preview = computed(() =>
  Array.isArray(props.model.preview) ? props.model.preview[0] : props.model.preview,
)

const container = ref<HTMLElement | null>(null)
const folderIcon = ref<InstanceType<typeof FolderIcon> | null>(null)

const badgeScale = computed(() => props.width / 200)

const { dragToAddModelNode } = useModelNodeAction()
</script>
