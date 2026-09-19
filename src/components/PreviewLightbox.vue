<template>
  <!--
    Full-screen preview viewer.

    Feature: previews used to be inert thumbnails - the only way to actually
    look at one was to leave the extension. Tapping a preview now opens this
    lightbox (teleported to <body>, above every dialog but below the toasts),
    with the same `<` / `>` paging as the card so a whole Civitai gallery can be
    browsed at full size. Escape, the backdrop and the close button dismiss it.
  -->
  <Teleport to="body">
    <div
      v-if="open"
      data-mm-lightbox
      class="mm-scope fixed inset-0 z-(--mm-z-lightbox) flex items-center justify-center bg-black/85 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      :aria-label="ariaLabel"
      @click.self="close"
    >
      <div class="relative flex max-h-[92vh] max-w-[92vw] items-center justify-center">
        <video
          v-if="isVideoUrl(current)"
          class="max-h-[92vh] max-w-[92vw] rounded-mm-card shadow-mm-3"
          :src="current"
          controls
          autoplay
          loop
          muted
          playsinline
        ></video>
        <img
          v-else
          class="max-h-[92vh] max-w-[92vw] rounded-mm-card object-contain shadow-mm-3"
          :src="current"
          :alt="ariaLabel"
        />
        <div
          v-if="items.length > 1"
          class="absolute -bottom-9 left-1/2 -translate-x-1/2 text-xs text-white/85 tabular-nums"
        >
          {{ index + 1 }} / {{ items.length }}
        </div>
      </div>

      <button
        v-if="items.length > 1"
        type="button"
        class="mm-transition absolute top-1/2 left-4 grid size-11 -translate-y-1/2 place-items-center rounded-full border border-white/20 bg-white/10 text-white backdrop-blur-md hover:bg-white/25 focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:outline-none active:scale-95"
        :aria-label="t('previousPreview')"
        :title="t('previousPreview')"
        @click.stop="prev"
      >
        <ChevronLeft class="size-6" />
      </button>
      <button
        v-if="items.length > 1"
        type="button"
        class="mm-transition absolute top-1/2 right-4 grid size-11 -translate-y-1/2 place-items-center rounded-full border border-white/20 bg-white/10 text-white backdrop-blur-md hover:bg-white/25 focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:outline-none active:scale-95"
        :aria-label="t('nextPreview')"
        :title="t('nextPreview')"
        @click.stop="next"
      >
        <ChevronRight class="size-6" />
      </button>
      <button
        type="button"
        class="mm-transition absolute top-4 right-4 grid size-10 place-items-center rounded-full border border-white/20 bg-white/10 text-white backdrop-blur-md hover:bg-white/25 focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:outline-none active:scale-95"
        :aria-label="t('close')"
        :title="t('close')"
        @click.stop="close"
      >
        <X class="size-5" />
      </button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight, X } from '@lucide/vue'
import { computed, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { isVideoUrl } from 'utils/media'

const props = withDefaults(
  defineProps<{
    open: boolean
    items?: string[]
    index?: number
  }>(),
  { items: () => [], index: 0 },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:index': [value: number]
}>()

const { t } = useI18n()
const ariaLabel = computed(() => t('previewFullscreen'))

const current = computed(() => props.items[props.index] ?? '')

const close = () => emit('update:open', false)
const prev = () => emit('update:index', (props.index - 1 + props.items.length) % props.items.length)
const next = () => emit('update:index', (props.index + 1) % props.items.length)

const onKey = (event: KeyboardEvent) => {
  if (!props.open) return
  if (event.key === 'Escape') close()
  else if (event.key === 'ArrowLeft' && props.items.length > 1) prev()
  else if (event.key === 'ArrowRight' && props.items.length > 1) next()
}

watch(
  () => props.open,
  open => {
    if (open) window.addEventListener('keydown', onKey)
    else window.removeEventListener('keydown', onKey)
  },
)

onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>
