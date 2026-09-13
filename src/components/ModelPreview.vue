<template>
  <div class="flex flex-col gap-4">
    <div>
      <div
        class="preview-aspect relative mx-auto w-full overflow-hidden rounded-lg"
        :style="$sm({ width: `${cardWidth}px` })"
      >
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
            @click.stop="prevPage"
          >
            <ChevronLeft class="size-4" />
          </button>
          <button
            type="button"
            class="mm-transition absolute top-1/2 right-2 z-10 -translate-y-1/2 rounded-full border border-mm-fg/12 bg-mm-bg/40 p-1 shadow-mm-glass-1 backdrop-blur-md hover:bg-mm-fg/15 focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none active:scale-95"
            :aria-label="$t('nextPreview')"
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
    </div>

    <div v-if="editable" class="flex flex-col gap-4 whitespace-nowrap">
      <div class="h-10"></div>
      <div
        :class="[
          'absolute flex h-10 items-center gap-4',
          $xl('left-0 translate-x-0', 'left-1/2 -translate-x-1/2'),
        ]"
      >
        <Button
          v-for="type in typeOptions"
          :key="type"
          :variant="currentType === type ? 'default' : 'secondary'"
          @click="currentType = type"
        >
          {{ $t(type) }}
        </Button>
      </div>

      <div v-show="currentType === 'network'">
        <div class="absolute left-0 w-full">
          <ResponseInput
            v-model="networkContent"
            prefix-icon="pi pi-globe"
            :allow-clear="true"
          ></ResponseInput>
        </div>
        <div class="h-10"></div>
      </div>

      <div v-show="currentType === 'local'">
        <ResponseFileUpload class="absolute left-0 h-24 w-full" @select="updateLocalContent">
        </ResponseFileUpload>
        <div class="h-24"></div>
      </div>
    </div>

    <PreviewLightbox
      v-model:open="lightboxOpen"
      v-model:index="lightboxIndex"
      :items="lightboxItems"
    />
  </div>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import { computed, ref } from 'vue'
import PreviewLightbox from 'components/PreviewLightbox.vue'
import PreviewVideo from 'components/PreviewVideo.vue'
import ResponseFileUpload from 'components/ResponseFileUpload.vue'
import ResponseImage from 'components/ResponseImage.vue'
import ResponseInput from 'components/ResponseInput.vue'
import { Button } from 'components/ui/button'
import { useConfig } from 'hooks/config'
import { useContainerQueries } from 'hooks/container'
import { useModelPreview } from 'hooks/model'
import { isVideoUrl } from 'utils/media'

const editable = defineModel<boolean>('editable')
const { cardWidth } = useConfig()

const {
  preview,
  typeOptions,
  currentType,
  defaultContent,
  defaultContentPage,
  networkContent,
  updateLocalContent,
  noPreviewContent,
  localContentType,
} = useModelPreview()

const { $sm, $xl } = useContainerQueries()

/** The gallery the `<` / `>` buttons page through (default source only). */
const canPage = computed(() => currentType.value === 'default' && defaultContent.value.length > 1)

/** What the preview area shows right now. */
const currentPreview = computed(() => {
  if (currentType.value === 'default') {
    return defaultContent.value[defaultContentPage.value]
  }
  return preview.value
})

const prevPage = () => {
  defaultContentPage.value =
    (defaultContentPage.value - 1 + defaultContent.value.length) % defaultContent.value.length
}

const nextPage = () => {
  defaultContentPage.value = (defaultContentPage.value + 1) % defaultContent.value.length
}

/* ---- lightbox ---------------------------------------------------------- */
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
