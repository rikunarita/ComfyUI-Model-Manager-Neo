<template>
  <div
    ref="container"
    :data-dragging="isDragging ? 'true' : 'false'"
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
        <!--
          Unified card look: folder cards keep the compact bottom strip while
          model cards render the large overlay caption (hidden on tiny card
          sizes). Every view uses this same default, so flat and folder views
          no longer drift apart visually.
        -->
        <div v-if="model.isFolder" class="flex justify-center overflow-hidden px-1">
          <span class="truncate">
            {{ model.basename }}
          </span>
        </div>
        <div v-else v-show="showModelName" class="pointer-events-none absolute top-0 size-full p-2">
          <div class="flex h-full flex-col justify-end text-lg">
            <div class="text-shadow line-clamp-3 font-bold break-all">
              {{ model.basename }}
            </div>
          </div>
        </div>
      </slot>
    </div>

    <div
      v-if="!model.isFolder && !selectable"
      data-draggable-overlay
      class="absolute top-0 left-0 size-full"
      draggable="true"
      @dragstart="isDragging = true"
      @dragend.stop="onDragEnd(model, $event)"
    ></div>

    <!--
      Multi-select checkbox (feature: "Select files"). Rendered only while the
      selection mode is on; it stops propagation so ticking a card never opens
      it or starts a drag.
    -->
    <button
      v-if="selectable"
      type="button"
      class="mm-transition absolute top-2 left-2 z-20 grid size-6 place-items-center rounded-full border backdrop-blur-md active:scale-90"
      :class="
        selected
          ? 'border-mm-accent/60 bg-mm-accent/80 text-mm-accent-fg shadow-mm-accent-1'
          : 'border-mm-fg/25 bg-mm-bg/50 text-transparent hover:border-mm-accent/60 hover:text-mm-fg/60'
      "
      :aria-label="selected ? $t('deselectModel') : $t('selectModel')"
      :aria-pressed="selected"
      @click.stop.prevent="$emit('toggle')"
      @dblclick.stop.prevent
    >
      <Check class="size-4" :stroke-width="3" />
    </button>

    <CardCornerControls :model="model" />
    <CardBadges v-if="!model.isFolder" :model="model" :scale="badgeScale" />

    <slot name="extra"></slot>
  </div>
</template>

<script setup lang="ts">
import { Check } from '@lucide/vue'
import { computed, ref } from 'vue'
import CardBadges from 'components/CardBadges.vue'
import CardCornerControls from 'components/CardCornerControls.vue'
import FolderIcon from 'components/FolderIcon.vue'
import PreviewVideo from 'components/PreviewVideo.vue'
import { useConfig } from 'hooks/config'
import { useModelNodeAction } from 'hooks/model'
import { type BaseModel } from 'types/typings'
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
  /** Selection mode: shows the round checkbox and disables drag-to-graph. */
  selectable?: boolean
  selected?: boolean
}

const props = withDefaults(defineProps<Props>(), { width: 200, selectable: false, selected: false })

defineEmits<{ toggle: [] }>()

const preview = computed(() =>
  Array.isArray(props.model.preview) ? props.model.preview[0] : props.model.preview,
)

const container = ref<HTMLElement | null>(null)
const folderIcon = ref<InstanceType<typeof FolderIcon> | null>(null)

/**
 * True while the card is being dragged to the graph.
 *
 * BUG FIX (reported as "hover/swipe makes unrelated elements glow"): the
 * hover-revealed glass buttons fade in whenever a card is hovered, and a
 * drag keeps the hover state alive for its whole duration - mid-drag the
 * glass buttons (with their backdrop blur) appeared over the type/size chips
 * and tinted them. `data-dragging` lets the grid suppress them while dragging.
 */
const isDragging = ref(false)

const onDragEnd = (model: BaseModel, event: DragEvent) => {
  isDragging.value = false
  dragToAddModelNode(model, event)
}

const badgeScale = computed(() => props.width / 200)
/** Caption/hover-column visibility rule, identical in every view. */
const { cardSize } = useConfig()
const showModelName = computed(() => cardSize.value.width > 120 && cardSize.value.height > 160)

const { dragToAddModelNode } = useModelNodeAction()
</script>
