<template>
  <div class="flex flex-col gap-4">
    <div>
      <div
        class="preview-aspect relative mx-auto w-full overflow-hidden rounded-lg"
        :style="$sm({ width: `${cardWidth}px` })"
      >
        <div
          v-if="
            preview && isVideoUrl(preview, currentType === 'local' ? localContentType : undefined)
          "
          class="size-full p-1 hover:p-0"
        >
          <PreviewVideo :src="preview" />
        </div>

        <ResponseImage v-else :src="preview" :error="noPreviewContent"></ResponseImage>

        <!-- Carousel replacement: simple slider -->
        <div
          v-if="defaultContent.length > 1"
          v-show="currentType === 'default'"
          class="absolute top-0 size-full"
        >
          <div class="size-full">
            <div
              v-if="isVideoUrl(defaultContent[defaultContentPage])"
              class="size-full p-1 hover:p-0"
            >
              <PreviewVideo :src="defaultContent[defaultContentPage]" />
            </div>
            <ResponseImage
              v-else
              :src="defaultContent[defaultContentPage]"
              :error="noPreviewContent"
            ></ResponseImage>
          </div>
          <!-- type="button": inside ModelContent's <form>, a bare <button>
               defaults to type="submit" and would save + close the editor. -->
          <button
            type="button"
            class="mm-transition absolute top-1/2 left-4 z-10 -translate-y-1/2 rounded-full border border-mm-fg/12 bg-mm-bg/40 p-1 shadow-mm-glass-1 backdrop-blur-md hover:bg-mm-fg/15"
            @click="prevPage"
          >
            <ChevronLeft class="size-4" />
          </button>
          <button
            type="button"
            class="mm-transition absolute top-1/2 right-4 z-10 -translate-y-1/2 rounded-full border border-mm-fg/12 bg-mm-bg/40 p-1 shadow-mm-glass-1 backdrop-blur-md hover:bg-mm-fg/15"
            @click="nextPage"
          >
            <ChevronRight class="size-4" />
          </button>
        </div>
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
  </div>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight } from '@lucide/vue'
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

const prevPage = () => {
  defaultContentPage.value =
    (defaultContentPage.value - 1 + defaultContent.value.length) % defaultContent.value.length
}

const nextPage = () => {
  defaultContentPage.value = (defaultContentPage.value + 1) % defaultContent.value.length
}
</script>
