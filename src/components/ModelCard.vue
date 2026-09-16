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

    <!--
      Top-right control row on EVERY card: the star toggle plus the ZipNN
      corner button. The star is an outline glyph when unstarred and a filled
      yellow star when starred; clicking toggles it. The ZipNN button is the
      shipped SVG artwork (same confirmation, same inverted colours for
      compressed models / bundle folders as the detail call-to-action); while
      its task runs it shows a circular progress ring (batch & delta included)
      instead of a plain spinner.
    -->
    <div class="absolute top-2 right-2 z-20 flex items-start gap-1">
      <button
        type="button"
        class="mm-transition grid size-7 shrink-0 place-items-center rounded-full border backdrop-blur-md active:scale-90"
        :class="
          starred
            ? 'border-mm-warning/60 bg-mm-bg/70 text-mm-warning shadow-mm-glass-1'
            : 'border-mm-fg/25 bg-mm-bg/50 text-mm-fg/70 hover:border-mm-warning/60 hover:text-mm-warning'
        "
        :title="starred ? $t('unstar') : $t('star')"
        :aria-label="starred ? $t('unstar') : $t('star')"
        :aria-pressed="starred"
        @click.stop.prevent="toggleStar"
        @dblclick.stop.prevent
      >
        <Star class="size-4" :class="starred && 'fill-current'" :stroke-width="2" />
      </button>
      <button
        v-if="zipnnApplicable"
        type="button"
        class="mm-transition mm-zipnn-button size-12 shrink-0 rounded-mm-ctl"
        :title="zipnnLabel"
        :aria-label="zipnnLabel"
        :disabled="zipnnRunning"
        @click.stop.prevent="requestZipnn"
        @dblclick.stop.prevent
      >
        <span v-if="zipnnRunning" class="relative grid size-full place-items-center">
          <svg viewBox="0 0 36 36" class="size-full -rotate-90">
            <circle
              cx="18"
              cy="18"
              r="15"
              fill="none"
              stroke="currentColor"
              stroke-width="4"
              class="text-mm-fg/25"
            />
            <circle
              cx="18"
              cy="18"
              r="15"
              fill="none"
              stroke="currentColor"
              stroke-width="4"
              stroke-linecap="round"
              :stroke-dasharray="`${(zipnnProgress * 94.25) / 100} 94.25`"
              class="text-mm-accent"
            />
          </svg>
          <span class="absolute text-[10px] leading-none font-bold text-mm-accent tabular-nums">
            {{ Math.round(zipnnProgress) }}%
          </span>
        </span>
        <img
          v-else
          :src="zipnnIcon"
          alt=""
          class="size-full rounded-mm-ctl"
          :class="zipnnInverted && 'hue-rotate-180 invert'"
        />
      </button>
    </div>

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
import { Check, Star } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import FolderIcon from 'components/FolderIcon.vue'
import PreviewVideo from 'components/PreviewVideo.vue'
import { useConfig } from 'hooks/config'
import { genModelFullName, useModelNodeAction } from 'hooks/model'
import { isFolderStarred, isModelStarred, toggleFolderStar, toggleModelStar } from 'hooks/stars'
import { useToast } from 'hooks/toast'
import {
  startZipnn,
  startZipnnBatch,
  startZipnnDeltaDecompress,
  zipnnRunningFor,
  zipnnState,
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
const { toast, confirm } = useToast()

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
  // Every folder except delta bundles is a batch target; type roots are
  // processed in place by the backend (no *_ZNN rename).
  if (isFolder.value) return !isDeltaFolderName(folderName.value)
  return isCompressedModel.value || props.model.extension === '.safetensors'
})
/** Direction of the folder batch: bundles decompress, type roots auto. */
const zipnnFolderMode = computed<'compress' | 'decompress' | 'auto'>(() => {
  if (isZnnFolderName(folderName.value)) return 'decompress'
  return isTypeRootFolder.value ? 'auto' : 'compress'
})
const zipnnInverted = computed(() => {
  if (isFolder.value) return isZnnFolderName(folderName.value)
  return isCompressedModel.value || isDeltaModel.value
})
const zipnnRunning = computed(() => zipnnRunningFor(modelKey.value))
/** 0-100, drives the circular progress ring on the corner button. */
const zipnnProgress = computed(() => zipnnState.progress)
const zipnnLabel = computed(() => {
  if (isFolder.value) {
    if (isZnnFolderName(folderName.value)) return t('zipnnBatchDecompress')
    return isTypeRootFolder.value ? t('zipnnBatch') : t('zipnnBatchCompress')
  }
  if (isDeltaModel.value) return t('zipnnDeltaDecompress')
  return isCompressedModel.value ? t('zipnnDecompress') : t('zipnnCompress')
})

const requestZipnn = () => {
  const model = props.model
  const key = modelKey.value
  if (isFolder.value) {
    const mode = zipnnFolderMode.value
    // type-root folders address themselves as '.' (their own base path)
    const folderRel = isTypeRootFolder.value ? '.' : genModelFullName(model)
    if (!model.type || !folderRel) {
      toast.add({ severity: 'warn', summary: t('zipnnBatchInvalidTarget'), life: 8000 })
      return
    }
    const message =
      mode === 'decompress'
        ? t('zipnnBatchConfirmDecompress', { name: folderName.value })
        : mode === 'auto'
          ? t('zipnnBatchConfirmAuto', { name: folderName.value })
          : t('zipnnBatchConfirmCompress', { name: folderName.value })
    confirm.require({
      message,
      header: zipnnLabel.value,
      icon: 'pi pi-info-circle',
      rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
      acceptProps: { label: zipnnLabel.value },
      accept: () => {
        void startZipnnBatch(
          mode,
          {
            type: model.type,
            pathIndex: model.pathIndex,
            folder: folderRel,
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
