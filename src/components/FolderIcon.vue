<script setup lang="ts">
/**
 * Glassmorphism folder icon with hover animations.
 *
 * The artwork lives in `assets/Folder-Icons/` as SMIL-animated SVGs. It is
 * inlined into the bundle with `?raw` and served through data URIs, so
 *   - no runtime fetch is needed (the ComfyUI extension path never matters),
 *   - every instance gets its OWN svg document, so the gradient ids inside
 *     the artwork can never collide between the many folder cards,
 *   - swapping the <img> node restarts the SMIL timeline, which is how the
 *     opening/closing animations replay on every hover.
 *
 * States: idle -> close-folder_beside-fit.svg (the regular look),
 * hover -> folder-opening-animation.svg, unhover -> folder-closing-animation.svg
 * (0.2 s delay + 1.35 s morph), then back to idle.
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import closedRaw from '../../assets/Folder-Icons/close-folder_beside-fit.svg?raw'
import closingRaw from '../../assets/Folder-Icons/folder-closing-animation.svg?raw'
import openingRaw from '../../assets/Folder-Icons/folder-opening-animation.svg?raw'

const toDataUri = (raw: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(raw)}`

const SOURCES = {
  idle: toDataUri(closedRaw),
  opening: toDataUri(openingRaw),
  closing: toDataUri(closingRaw),
} as const

/** 0.2s begin delay + 1.35s morph, with a little slack. */
const CLOSING_MS = 1700

const state = ref<'idle' | 'opening' | 'closing'>('idle')
const seq = ref(0)
let timer: ReturnType<typeof setTimeout> | undefined

const enter = () => {
  if (timer) clearTimeout(timer)
  seq.value++
  state.value = 'opening'
}

const leave = () => {
  if (timer) clearTimeout(timer)
  seq.value++
  state.value = 'closing'
  timer = setTimeout(() => {
    state.value = 'idle'
  }, CLOSING_MS)
}

defineExpose({ enter, leave })

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})

const src = computed(() => SOURCES[state.value])
</script>

<template>
  <!-- :key forces a fresh <img> (fresh SMIL document) per state change -->
  <img :key="seq" :src="src" class="size-full object-contain" alt="" draggable="false" />
</template>
