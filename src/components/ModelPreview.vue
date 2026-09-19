<template>
  <div :class="['flex min-w-0 flex-col gap-4', layout === 'stacked' ? 'w-full' : 'shrink-0']">
    <!--
      GALLERY + PREVIEW ARRANGEMENT.

      The edit-mode gallery used to be a single horizontally scrolling strip
      parked BELOW the preview. That strip was a scroll container, so two
      things broke in the download dialog:

      1. its min-content width was the SUM of every non-shrinking thumbnail,
         which inflated this whole column far beyond the dialog body; the
         centred column then bled out of both dialog edges (left edge and the
         per-thumbnail controls clipped, only the right side recoverable by
         scrolling) - the "panel area and visible area are offset" defect;
      2. `overflow-x-auto` also clips vertically, so the little move/remove
         buttons that sit `-top-1.5` on each thumbnail were cut off.

      The gallery is now a WRAPPING GRID (no scroll container, padded so the
      per-thumbnail controls are never clipped) and, in the stacked layout
      used by the download dialog, it sits RIGHT of the single preview image
      (preview left, gallery right; below the `md` container breakpoint the
      row folds into a column, preview first). The preview block comes first
      in the DOM so the visual and tab order agree in both directions.
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
          v-if="
            currentPreview &&
            isVideoUrl(currentPreview, currentType === 'local' ? localContentType : undefined)
          "
          class="size-full cursor-zoom-in p-1 hover:p-0"
          @click="openLightbox"
        >
          <PreviewVideo :src="currentPreview" />
        </div>
        <div v-else class="size-full cursor-zoom-in" @click="openLightbox">
          <ResponseImage :src="currentPreview" :error="noPreviewContent"></ResponseImage>
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
           the card's primary preview. -->
      <div
        v-if="showGallery"
        :class="[
          'grid content-start gap-2 p-1.5',
          'grid-cols-[repeat(auto-fill,minmax(3.5rem,1fr))]',
          stackedEditable ? $md('min-w-0 flex-1', 'w-full') : 'w-full',
        ]"
        :style="layout === 'auto' ? { maxWidth: `${cardWidth}px` } : undefined"
      >
        <div
          v-for="(url, index) in defaultContent"
          :key="`${url}-${index}`"
          class="relative"
          :class="index === defaultContentPage && 'ring-2 ring-mm-accent'"
        >
          <img
            :src="url"
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

    <div v-if="sourceControlsVisible" class="flex flex-col gap-4 whitespace-nowrap">
      <!--
        LAYOUT FIX: the source-type switcher / network input / local upload
        used to be `position: absolute` overlays parked over empty spacer divs
        (`h-10` / `h-24`), anchored to whichever positioned ancestor happened
        to exist. Inside the download dialog that anchor was the content row,
        so the controls could land anywhere (or nowhere). Everything is plain
        flow content now - the block always sits directly under the gallery.
      -->
      <div class="flex min-h-9 flex-wrap items-center gap-4">
        <Button
          v-for="type in typeOptions"
          :key="type"
          :variant="currentType === type ? 'default' : 'secondary'"
          @click="currentType = type"
        >
          {{ $t(type) }}
        </Button>
      </div>

      <ResponseInput
        v-show="currentType === 'network'"
        v-model="networkContent"
        prefix-icon="pi pi-globe"
        :allow-clear="true"
      ></ResponseInput>

      <ResponseFileUpload
        v-show="currentType === 'local'"
        class="h-24 w-full"
        @select="updateLocalContent"
      >
      </ResponseFileUpload>
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
import ResponseFileUpload from 'components/ResponseFileUpload.vue'
import ResponseImage from 'components/ResponseImage.vue'
import ResponseInput from 'components/ResponseInput.vue'
import { Button } from 'components/ui/button'
import { useConfig } from 'hooks/config'
import { useContainerQueries } from 'hooks/container'
import { useModelBaseInfo, useModelPreview } from 'hooks/model'
import { isVideoUrl } from 'utils/media'

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
  typeOptions,
  currentType,
  defaultContent,
  defaultContentPage,
  movePreview,
  removePreview,
  networkContent,
  updateLocalContent,
  noPreviewContent,
  localContentType,
} = useModelPreview()

const { $sm, $md } = useContainerQueries()

/** Edit mode of the stacked (download dialog) layout: preview left, gallery right. */
const stackedEditable = computed(() => props.layout === 'stacked' && Boolean(editable.value))

/**
 * The stacked (download task) layout no longer offers the preview source
 * switcher (default / network / local / none) nor the local add-tile: the
 * gallery resolved from the model page is the single preview source there.
 * The model detail editor keeps the full controls.
 */
const sourceControlsVisible = computed(() => Boolean(editable.value) && props.layout !== 'stacked')
const canAddLocal = computed(() => props.layout !== 'stacked')

/** The gallery editor is meaningful for the saved ("default") source; the
 *  grid also renders (with just the add-tile) when no preview exists yet. */
const showGallery = computed(() => Boolean(editable.value) && currentType.value === 'default')

/** The gallery the `<` / `>` buttons page through (default source only). */
const canPage = computed(() => currentType.value === 'default' && defaultContent.value.length > 1)

/** What the preview area shows right now. */
const currentPreview = computed(() => {
  if (currentType.value === 'default') {
    return defaultContent.value[defaultContentPage.value]
  }
  return preview.value
})

/**
 * Preview frame classes: in the stacked edit row the frame is the fixed-width
 * left-hand side of the row (and the first block when the row folds into a
 * column); everywhere else it stays a centred, card-width block.
 */
const previewClass = computed(() => [
  'preview-aspect',
  'relative',
  'overflow-hidden',
  'rounded-lg',
  stackedEditable.value
    ? $md(showGallery.value ? 'shrink-0' : 'mx-auto shrink-0', 'w-full')
    : ['mx-auto', 'w-full'],
])

const previewStyle = computed(() => {
  if (stackedEditable.value) {
    return $md({ width: `${cardWidth}px` }, { width: '100%' })
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
  if (canPage.value) return defaultContent.value
  return currentPreview.value ? [currentPreview.value] : []
})

const openLightbox = () => {
  if (!currentPreview.value) return
  lightboxIndex.value = canPage.value ? defaultContentPage.value : 0
  lightboxOpen.value = true
}
</script>
