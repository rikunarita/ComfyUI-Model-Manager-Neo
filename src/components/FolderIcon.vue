<script setup lang="ts">
/**
 * Flat-aurora glass folder icon with a hover float.
 *
 * The artwork lives in `assets/Folder-Icons/` as a plain, SMIL-free SVG served
 * cached through `/model-manager/assets/<name>.svg`. The old SMIL
 * opening/closing morphs (and their one-second hover gates) are gone: hovering
 * a card starts a plain CSS floating bob; leaving settles the folder at once.
 * A sparkle hover variant existed for a day; real-device QA found it cheapened
 * the UI, so the icon stays sparkle-free.
 */
import { ref } from 'vue'
import { assetUrl } from 'utils/media'

const SRC = assetUrl('folder-card')

const hovering = ref(false)

const enter = () => {
  hovering.value = true
}

const leave = () => {
  hovering.value = false
}

defineExpose({ enter, leave })
</script>

<template>
  <img
    :src="SRC"
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
