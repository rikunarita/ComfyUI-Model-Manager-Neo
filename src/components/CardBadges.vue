<script setup lang="ts">
import { type BaseModel } from 'types/typings'
import { bytesToSize } from 'utils/common'

interface Props {
  model: BaseModel
  /** Badges scale with the card; 1 at the 200 px reference width. */
  scale: number
}
defineProps<Props>()
</script>

<template>
  <!--
    Glassmorphism type/size chips at the preview's bottom-right (the ZipNN
    corner button owns the top-right corner).
  -->
  <div
    class="pointer-events-none absolute right-2 bottom-8 flex flex-col items-end gap-1"
    :style="{
      transform: `scale(${scale})`,
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
</template>
