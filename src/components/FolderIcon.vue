<script setup lang="ts">
/**
 * Flat-aurora glass folder icon with a hover float.
 *
 * The artwork lives in `assets/Folder-Icons/` as plain, SMIL-free SVGs, served
 * cached through `/model-manager/assets/<name>.svg`:
 *   - idle  -> close-folder_beside-fit.svg (the regular look),
 *   - hover -> folder-hover.svg (turquoise sparkles rise above the folder).
 *
 * The old SMIL opening/closing morphs (and their one-second hover gates) are
 * gone: hovering a card swaps the artwork and starts a plain CSS floating
 * bob; leaving swaps back and the folder settles at once.
 */
import { computed, ref } from 'vue'
import { assetUrl } from 'utils/media'

const SOURCES = {
  idle: assetUrl('folder-closed'),
  hover: assetUrl('folder-hover'),
} as const

const hovering = ref(false)

const enter = () => {
  hovering.value = true
}

const leave = () => {
  hovering.value = false
}

defineExpose({ enter, leave })

const src = computed(() => (hovering.value ? SOURCES.hover : SOURCES.idle))
</script>

<template>
  <img
    :src="src"
    :class="['size-full object-contain', hovering && 'mm-folder-float']"
    alt=""
    draggable="false"
    decoding="async"
  />
</template>

<style scoped>
/* Gentle bob while the pointer rests on the folder card. */
.mm-folder-float {
  animation: mm-folder-float 1.9s ease-in-out infinite;
}

@keyframes mm-folder-float {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-5%);
  }
}
</style>
