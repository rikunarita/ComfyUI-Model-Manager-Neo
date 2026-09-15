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
        <div class="flex justify-center overflow-hidden px-1">
          <span class="truncate">
            {{ model.basename }}
          </span>
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

    <!--
      Star badge (top-left, only while starred). Clicking it toggles the star;
      in selection mode it shifts right so the checkbox keeps its corner.
    -->
    <button
      v-if="starred"
      type="button"
      class="mm-transition absolute top-2 z-20 grid size-6 place-items-center rounded-full border border-mm-warning/50 bg-mm-bg/70 text-mm-warning shadow-mm-glass-1 backdrop-blur-md active:scale-90"
      :class="selectable ? 'left-12' : 'left-2'"
      :title="$t('unstar')"
      :aria-label="$t('unstar')"
      :aria-pressed="true"
      @click.stop.prevent="toggleStar"
      @dblclick.stop.prevent
    >
      <Star class="size-4 fill-current" :stroke-width="2" />
    </button>

    <!--
      ZipNN corner button (top-right): the shipped SVG artwork, exactly like
      the model-detail call-to-action (same confirmation, same inverted
      colours for compressed / bundle folders, same progress state). Folders
      run the batch job; `*_DeltaZNN` delta files restore through their base.
    -->
    <button
      v-if="zipnnApplicable"
      type="button"
      class="mm-transition mm-zipnn-button absolute top-2 right-2 z-20 size-10 rounded-mm-ctl"
      :title="zipnnLabel"
      :aria-label="zipnnLabel"
      :disabled="zipnnRunning"
      @click.stop.prevent="requestZipnn"
      @dblclick.stop.prevent
    >
      <Loader2 v-if="zipnnRunning" class="size-6 animate-spin text-mm-accent" />
      <img
        v-else
        :src="zipnnIcon"
        alt=""
        class="size-full rounded-mm-ctl"
        :class="zipnnInverted && 'hue-rotate-180 invert'"
      />
    </button>

    <!-- Glassmorphism badges (type / size): moved to the preview's bottom-right
         so the ZipNN corner button owns the top-right corner. -->
    <div
      v-if="!model.isFolder"
      class="pointer-events-none absolute right-2 bottom-8 flex flex-col items-end gap-1"
      :style="{
        transform: `scale(${badgeScale})`,
        transformOrigin: 'right bottom',
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
import { Check, Loader2, Star } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import FolderIcon from 'components/FolderIcon.vue'
import PreviewVideo from 'components/PreviewVideo.vue'
import { genModelFullName, useModelNodeAction } from 'hooks/model'
import { isFolderStarred, isModelStarred, toggleFolderStar, toggleModelStar } from 'hooks/stars'
import { useToast } from 'hooks/toast'
import {
  startZipnn,
  startZipnnBatch,
  startZipnnDeltaDecompress,
  zipnnRunningFor,
} from 'hooks/zipnn'
import { type BaseModel } from 'types/typings'
import { bytesToSize } from 'utils/common'
import { isVideoUrl, assetUrl } from 'utils/media'
import { genModelKey, isDeltaFolderName, isZnnFolderName } from 'utils/model'

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

const { t } = useI18n()
const { confirm } = useToast()

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

const { dragToAddModelNode } = useModelNodeAction()

/* ---- star badge ------------------------------------------------------ */
const modelKey = computed(() => genModelKey(props.model))
const starred = computed(() =>
  props.model.isFolder ? isFolderStarred(modelKey.value) : isModelStarred(modelKey.value),
)
const toggleStar = () => {
  if (props.model.isFolder) toggleFolderStar(modelKey.value)
  else toggleModelStar(modelKey.value)
}

/* ---- ZipNN corner button --------------------------------------------- */
const zipnnIcon = assetUrl('zipnn-button')
const isFolder = computed(() => Boolean(props.model.isFolder))
const folderName = computed(() => props.model.basename)
const isDeltaModel = computed(() => props.model.extension === '.znn')
const isCompressedModel = computed(() => props.model.basename.endsWith('.znn'))
/** Type-root folder cards (the library's top level) never batch-process. */
const isTypeRootFolder = computed(
  () => isFolder.value && !props.model.subFolder && props.model.basename === props.model.type,
)
const zipnnApplicable = computed(() => {
  if (isFolder.value) return !isDeltaFolderName(folderName.value) && !isTypeRootFolder.value
  return isCompressedModel.value || props.model.extension === '.safetensors'
})
const zipnnInverted = computed(() => {
  if (isFolder.value) return isZnnFolderName(folderName.value)
  return isCompressedModel.value || isDeltaModel.value
})
const zipnnRunning = computed(() => zipnnRunningFor(modelKey.value))
const zipnnLabel = computed(() => {
  if (isFolder.value) {
    return isZnnFolderName(folderName.value) ? t('zipnnBatchDecompress') : t('zipnnBatchCompress')
  }
  if (isDeltaModel.value) return t('zipnnDeltaDecompress')
  return isCompressedModel.value ? t('zipnnDecompress') : t('zipnnCompress')
})

const requestZipnn = () => {
  const model = props.model
  const key = modelKey.value
  if (isFolder.value) {
    const decompressing = isZnnFolderName(folderName.value)
    confirm.require({
      message: decompressing
        ? t('zipnnBatchConfirmDecompress', { name: folderName.value })
        : t('zipnnBatchConfirmCompress', { name: folderName.value }),
      header: decompressing ? t('zipnnBatchDecompress') : t('zipnnBatchCompress'),
      icon: 'pi pi-info-circle',
      rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
      acceptProps: { label: decompressing ? t('zipnnBatchDecompress') : t('zipnnBatchCompress') },
      accept: () => {
        void startZipnnBatch(
          decompressing ? 'decompress' : 'compress',
          {
            type: model.type,
            pathIndex: model.pathIndex,
            folder: genModelFullName(model),
          },
          key,
        )
      },
      reject: () => {},
    })
    return
  }
  if (isDeltaModel.value) {
    confirm.require({
      message: t('zipnnDeltaConfirmDecompress', { name: `${model.basename}${model.extension}` }),
      header: t('zipnnDeltaDecompress'),
      icon: 'pi pi-info-circle',
      rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
      acceptProps: { label: t('zipnnDeltaDecompress') },
      accept: () => {
        void startZipnnDeltaDecompress(
          {
            type: model.type,
            pathIndex: model.pathIndex,
            fullname: genModelFullName(model),
          },
          key,
        )
      },
      reject: () => {},
    })
    return
  }
  const compressing = !isCompressedModel.value
  confirm.require({
    message: compressing ? t('zipnnConfirmCompress') : t('zipnnConfirmDecompress'),
    header: compressing ? t('zipnnCompress') : t('zipnnDecompress'),
    icon: 'pi pi-info-circle',
    rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
    acceptProps: { label: compressing ? t('zipnnCompress') : t('zipnnDecompress') },
    accept: () => {
      void startZipnn(
        compressing ? 'compress' : 'decompress',
        {
          type: model.type,
          pathIndex: model.pathIndex,
          fullname: genModelFullName(model),
        },
        key,
      )
    },
    reject: () => {},
  })
}
</script>
