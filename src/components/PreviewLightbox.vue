<template>
  <!--
    Full-screen preview viewer.

    Feature: previews used to be inert thumbnails - the only way to actually
    look at one was to leave the extension. Tapping a preview now opens this
    lightbox (teleported to <body>, above every dialog but below the toasts),
    with the same `<` / `>` paging as the card so a whole Civitai gallery can
    be browsed at full size. Escape, the backdrop and the close button dismiss
    it. When the preview belongs to a Civitai model version the generation
    metadata (prompt, sampler, steps, seed, resources, …) is fetched and
    rendered beside the image: image left, parsed metadata right.
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
      <div class="relative flex max-h-[92vh] max-w-[92vw] items-center justify-center gap-4">
        <div class="relative flex items-center justify-center">
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

        <!-- Generation metadata of the Civitai image (image left / meta right). -->
        <aside
          v-if="meta"
          class="flex max-h-[92vh] w-80 shrink-0 flex-col gap-3 overflow-y-auto rounded-mm-card border border-white/15 bg-black/60 p-4 text-white backdrop-blur-md"
        >
          <div class="text-sm font-semibold">{{ t('metaTitle') }}</div>
          <div v-if="meta.prompt" class="flex flex-col gap-1">
            <span class="text-xs text-white/65">{{ t('metaPrompt') }}</span>
            <span class="text-xs whitespace-pre-wrap">{{ meta.prompt }}</span>
          </div>
          <div v-if="meta.negativePrompt" class="flex flex-col gap-1">
            <span class="text-xs text-white/65">{{ t('metaNegative') }}</span>
            <span class="text-xs whitespace-pre-wrap">{{ meta.negativePrompt }}</span>
          </div>
          <div class="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
            <template v-for="row in settingRows" :key="row.label">
              <span class="text-white/65">{{ row.label }}</span>
              <span class="truncate text-right" :title="row.value">{{ row.value }}</span>
            </template>
          </div>
          <div v-if="meta.Model" class="flex flex-col gap-1">
            <span class="text-xs text-white/65">{{ t('metaModel') }}</span>
            <span class="text-xs">{{ meta.Model }}</span>
          </div>
          <div v-if="resourceRows.length" class="flex flex-col gap-1">
            <span class="text-xs text-white/65">{{ t('metaResources') }}</span>
            <ul class="flex flex-col gap-1 text-xs">
              <li v-for="res in resourceRows" :key="res.name" class="flex justify-between gap-2">
                <span class="truncate" :title="res.name">{{ res.name }}</span>
                <span class="shrink-0 text-white/65">{{ res.detail }}</span>
              </li>
            </ul>
          </div>
        </aside>
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
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { request } from 'hooks/request'
import { isVideoUrl } from 'utils/media'

const props = withDefaults(
  defineProps<{
    open: boolean
    items?: string[]
    index?: number
    /** Civitai model-version id of the gallery; enables the metadata panel. */
    civitaiVersionId?: number | null
  }>(),
  { items: () => [], index: 0, civitaiVersionId: null },
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

/* ---- Civitai generation metadata --------------------------------------- */
const meta = ref<Record<string, any> | null>(null)

/** Scalar meta rows, in a stable order, skipping absent values. */
const settingRows = computed(() => {
  const m = meta.value
  if (!m) return []
  const rows: { label: string; value: string }[] = []
  const push = (label: string, value: unknown) => {
    if (value === undefined || value === null || value === '') return
    rows.push({ label, value: String(value) })
  }
  push(t('metaSampler'), m.sampler)
  push(t('metaSteps'), m.steps)
  push(t('metaCfg'), m.cfgScale)
  push(t('metaSeed'), m.seed)
  push(t('metaClip'), m.clipSkip)
  push(t('metaSize'), m.size)
  return rows
})

/** meta.resources → name + type/weight detail rows (best effort). */
const resourceRows = computed(() => {
  const list = meta.value?.resources
  if (!Array.isArray(list)) return []
  return list
    .map(entry => {
      const name = typeof entry?.name === 'string' ? entry.name : ''
      if (!name) return null
      const parts = [entry.type, entry.weight !== undefined ? `×${entry.weight}` : ''].filter(
        Boolean,
      )
      return { name, detail: parts.join(' ') }
    })
    .filter((row): row is { name: string; detail: string } => row !== null)
})

watch(
  () => [props.open, props.index, props.civitaiVersionId, current.value] as const,
  async ([open, , versionId, url]) => {
    meta.value = null
    if (!open || !versionId || !url) return
    try {
      const result = await request(
        `/civitai/image-meta?model-version-id=${versionId}&url=${encodeURIComponent(url)}`,
      )
      meta.value = result && typeof result === 'object' ? result : null
    } catch {
      meta.value = null
    }
  },
  { immediate: true },
)

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
