<template>
  <div :class="['flex min-w-0 flex-col gap-4', layout === 'stacked' ? 'w-full' : 'shrink-0']">
    <!--
      GALLERY + PREVIEW ARRANGEMENT.

      The edit-mode gallery is a single horizontally scrolling strip (inline
      scroll): fixed-size thumbnails in one row, so a long gallery never
      grows the column past the dialog and never wraps into a tall block.
      The strip is a scroll container with `min-w-0` plus an explicit width
      ceiling (the card width in the detail row, the free row space in the
      stacked download layout), and its padding keeps the per-thumbnail
      move/remove buttons (which sit `-top-1.5` on each tile) unclipped.
      In the stacked layout used by the download dialog the strip sits
      RIGHT of the single preview image (preview left, gallery right; below
      the `md` container breakpoint the row folds into a column, preview
      first). In the detail window's edit mode the preview shrinks to 4/5 of
      the card width and hugs the left edge while the strip runs beside /
      below it. The preview block comes first in the DOM so the visual and
      tab order agree in both directions.
    -->
    <div
      :class="[
        'flex min-w-0 gap-4',
        stackedEditable ? ['items-start', $md('flex-row', 'flex-col')] : 'flex-col',
      ]"
    >
      <div :class="previewClass" :style="previewStyle">
        <!--
          The visible media is the *current page* of the gallery. The old
          markup stacked a second copy of the current page on top of the base
          image just to host the arrows; the arrows now sit directly on the
          single media element.
        -->
        <div
          v-if="currentPreview && isVideoUrl(currentPreview)"
          class="size-full cursor-zoom-in p-1 hover:p-0"
          @click="openLightbox"
        >
          <PreviewVideo :src="currentPreviewSrc" />
        </div>
        <div v-else class="size-full cursor-zoom-in" @click="openLightbox">
          <ResponseImage :src="currentPreviewSrc" :error="noPreviewContent"></ResponseImage>
        </div>

        <!--
          Gallery paging: `<` / `>` icon buttons on the preview area itself, in
          edit *and* read-only mode, whenever the model has more than one
          preview (feature: every preview is kept now, so this is reachable on
          saved models too).
        -->
        <template v-if="canPage">
          <button
            type="button"
            class="mm-transition absolute top-1/2 left-2 z-10 -translate-y-1/2 rounded-full border border-mm-fg/12 bg-mm-bg/40 p-1 shadow-mm-glass-1 backdrop-blur-md hover:bg-mm-fg/15 focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none active:scale-95"
            :aria-label="$t('previousPreview')"
            :title="$t('previousPreview')"
            @click.stop="prevPage"
          >
            <ChevronLeft class="size-4" />
          </button>
          <button
            type="button"
            class="mm-transition absolute top-1/2 right-2 z-10 -translate-y-1/2 rounded-full border border-mm-fg/12 bg-mm-bg/40 p-1 shadow-mm-glass-1 backdrop-blur-md hover:bg-mm-fg/15 focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none active:scale-95"
            :aria-label="$t('nextPreview')"
            :title="$t('nextPreview')"
            @click.stop="nextPage"
          >
            <ChevronRight class="size-4" />
          </button>
          <div
            class="absolute right-2 bottom-2 z-10 rounded-full border border-mm-fg/12 bg-mm-bg/50 px-2 py-0.5 text-xs text-mm-fg tabular-nums backdrop-blur-md"
          >
            {{ defaultContentPage + 1 }} / {{ defaultContent.length }}
          </div>
        </template>
      </div>

      <!-- Gallery management (edit mode): pick the primary preview, reorder
           entries and drop single images. The page left open on save becomes
           the card's primary preview. The strip scrolls INLINE (horizontal)
           so a long gallery never grows the column past the dialog. -->
      <div
        v-if="showGallery"
        :class="[
          'flex min-w-0 gap-2 overflow-x-auto p-2',
          stackedEditable ? $md('min-w-0 flex-1', 'w-full') : 'w-full',
        ]"
        :style="layout === 'auto' ? { maxWidth: `${cardWidth}px` } : undefined"
      >
        <div
          v-for="(url, index) in defaultContent"
          :key="`${url}-${index}`"
          class="relative w-16 shrink-0"
          :class="index === defaultContentPage && 'ring-2 ring-mm-accent'"
        >
          <img
            :src="withPreviewBust(url, previewBust)"
            class="aspect-square w-full cursor-pointer rounded-mm-ctl object-cover"
            alt=""
            :title="$t('previewPickPrimary')"
            @click="defaultContentPage = index"
          />
          <div class="absolute -top-1.5 -right-1.5 flex gap-0.5">
            <button
              type="button"
              class="grid size-4 place-items-center rounded-full border border-mm-fg/25 bg-mm-bg/80 text-mm-fg backdrop-blur-md hover:text-mm-accent"
              :title="$t('previewMoveLeft')"
              :aria-label="$t('previewMoveLeft')"
              @click.stop="movePreview(index, -1)"
            >
              <ChevronLeft class="size-3" />
            </button>
            <button
              type="button"
              class="grid size-4 place-items-center rounded-full border border-mm-fg/25 bg-mm-bg/80 text-mm-fg backdrop-blur-md hover:text-mm-accent"
              :title="$t('previewMoveRight')"
              :aria-label="$t('previewMoveRight')"
              @click.stop="movePreview(index, 1)"
            >
              <ChevronRight class="size-3" />
            </button>
            <button
              type="button"
              class="grid size-4 place-items-center rounded-full border border-mm-danger/40 bg-mm-bg/80 text-mm-danger backdrop-blur-md hover:bg-mm-danger/20"
              :title="$t('previewRemove')"
              :aria-label="$t('previewRemove')"
              @click.stop="removePreview(index)"
            >
              <X class="size-3" />
            </button>
          </div>
        </div>

        <!--
          Add-tile at the END of the gallery: picks local image file(s) and
          appends them to the gallery like any other entry (object URLs; the
          save path converts them to uploaded preview files).
        -->
        <button
          v-if="canAddLocal"
          type="button"
          class="grid aspect-square w-full place-items-center rounded-mm-ctl border-2 border-dashed border-mm-border text-mm-muted-fg hover:border-mm-accent/60 hover:bg-mm-surface-hover hover:text-mm-accent"
          :title="$t('previewAdd')"
          :aria-label="$t('previewAdd')"
          @click="pickPreviewFiles"
        >
          <Plus class="size-5" />
        </button>
      </div>
    </div>

    <PreviewLightbox
      v-model:open="lightboxOpen"
      v-model:index="lightboxIndex"
      :items="lightboxItems"
      :civitai-version-id="civitaiVersionId"
    />
  </div>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight, Plus, X } from '@lucide/vue'
import { computed, ref } from 'vue'
import PreviewLightbox from 'components/PreviewLightbox.vue'
import PreviewVideo from 'components/PreviewVideo.vue'
import ResponseImage from 'components/ResponseImage.vue'
import { useConfig } from 'hooks/config'
import { useContainerQueries } from 'hooks/container'
import { previewBust, useModelBaseInfo, useModelPreview } from 'hooks/model'
import { isVideoUrl, withPreviewBust } from 'utils/media'

interface Props {
  /**
   * `auto`    – the model detail window: this column keeps the width of the
   *             preview card (capped by the dialog) and the gallery wraps
   *             underneath the preview.
   * `stacked` – the download task window: full-width column; in edit mode the
   *             preview image sits left of the gallery grid.
   */
  layout?: 'auto' | 'stacked'
}

const props = withDefaults(defineProps<Props>(), {
  layout: 'auto',
})

const editable = defineModel<boolean>('editable')
const { cardWidth } = useConfig()

const {
  preview,
  defaultContent,
  defaultContentPage,
  movePreview,
  removePreview,
  noPreviewContent,
} = useModelPreview()

const { $sm, $md } = useContainerQueries()

/** Edit mode of the stacked (download dialog) layout: preview left, gallery right. */
const stackedEditable = computed(() => props.layout === 'stacked' && Boolean(editable.value))

/** Edit mode of the detail window: the preview shrinks to 4/5 of the card
 *  width and hugs the left edge while the gallery strip scrolls inline. */
const editAuto = computed(() => props.layout === 'auto' && Boolean(editable.value))
const editPreviewWidth = computed(() => Math.round((cardWidth * 4) / 5))

/** The gallery is the single preview source everywhere; the historical
 *  default / network / local / none switcher no longer exists. */
const canAddLocal = computed(() => props.layout !== 'stacked')

/** The gallery editor is the preview editor (there is one source). */
const showGallery = computed(() => Boolean(editable.value))

/** The gallery the `<` / `>` buttons page through. */
const canPage = computed(() => defaultContent.value.length > 1)

/** What the preview area shows right now: the current gallery page. */
const currentPreview = computed(() => preview.value)
/** Cache-busted source: a save rewrites bytes behind unchanged preview URLs. */
const currentPreviewSrc = computed(() => withPreviewBust(currentPreview.value, previewBust.value))

/**
 * Preview frame classes: in the stacked edit row the frame is the fixed-width
 * left-hand side of the row (and the first block when the row folds into a
 * column); in the detail window's EDIT mode the (smaller) frame hugs the
 * left edge so the gallery strip beside/below it owns the remaining width;
 * everywhere else it stays a centred, card-width block.
 */
const previewClass = computed(() => [
  'preview-aspect',
  'relative',
  'overflow-hidden',
  'rounded-lg',
  stackedEditable.value
    ? $md(showGallery.value ? 'shrink-0' : 'mx-auto shrink-0', 'w-full')
    : editAuto.value
      ? ['mr-auto', 'w-full']
      : ['mx-auto', 'w-full'],
])

const previewStyle = computed(() => {
  if (stackedEditable.value) {
    return $md({ width: `${cardWidth}px` }, { width: '100%' })
  }
  if (editAuto.value) {
    // Edit mode: 4/5 of the card width (the gallery strip keeps the rest).
    return $sm({ width: `${editPreviewWidth.value}px` })
  }
  return $sm({ width: `${cardWidth}px` })
})

const prevPage = () => {
  defaultContentPage.value =
    (defaultContentPage.value - 1 + defaultContent.value.length) % defaultContent.value.length
}

/**
 * The gallery's add-tile: appends local image file(s) to the gallery. The
 * object URLs behave like any other preview URL (they render immediately and
 * are converted to uploaded preview files on save).
 */
const pickPreviewFiles = () => {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*'
  input.multiple = true
  input.onchange = () => {
    const files = input.files
    if (!files || files.length === 0) return
    const urls = Array.from(files).map(file => URL.createObjectURL(file))
    defaultContent.value = [...defaultContent.value, ...urls]
    defaultContentPage.value = defaultContent.value.length - 1
  }
  input.click()
}

const nextPage = () => {
  defaultContentPage.value = (defaultContentPage.value + 1) % defaultContent.value.length
}

/* ---- lightbox ---------------------------------------------------------- */
const baseInfo = useModelBaseInfo()

/**
 * Civitai model-version id recorded in the model page URL of the notes
 * (`…/models/<id>?modelVersionId=<vid>`); enables the lightbox's generation
 * metadata panel. Null for models without a Civitai origin.
 */
const civitaiVersionId = computed<number | null>(() => {
  const page = (baseInfo.model.value as { modelPage?: string } | undefined)?.modelPage
  if (!page) return null
  try {
    const vid = new URL(page).searchParams.get('modelVersionId')
    const parsed = vid ? Number(vid) : NaN
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null
  } catch {
    return null
  }
})

const lightboxOpen = ref(false)
const lightboxIndex = ref(0)

const lightboxItems = computed(() => {
  const urls = canPage.value
    ? defaultContent.value
    : currentPreview.value
      ? [currentPreview.value]
      : []
  return urls.map(url => withPreviewBust(url, previewBust.value) as string)
})

const openLightbox = () => {
  if (!currentPreview.value) return
  lightboxIndex.value = canPage.value ? defaultContentPage.value : 0
  lightboxOpen.value = true
}
</script>
