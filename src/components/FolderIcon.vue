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
 * hover >= 1 s -> folder-opening-animation.svg, unhover >= 1 s ->
 * folder-closing-animation.svg (0.2 s delay + 1.35 s morph), then idle.
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import { assetUrl } from 'utils/media'

/**
 * The artwork is served over HTTP with an ETag + max-age, so the browser
 * decodes each animation once per session and every folder card shares the
 * cached copy. Swapping `<img src>` still restarts the SMIL timeline, which is
 * how the opening/closing morphs replay on hover.
 */
const SOURCES = {
  idle: assetUrl('folder-closed'),
  opening: assetUrl('folder-opening'),
  closing: assetUrl('folder-closing'),
} as const

/** 0.2s begin delay + 1.35s morph, with a little slack. */
const CLOSING_MS = 1700

/**
 * The animations are gated on sustained hover: the opening morph starts only
 * after the pointer rested on the folder for a full second, and the closing
 * morph only after it stayed away for a full second - casual pass-overs no
 * longer make the folder flap.
 */
const HOVER_GATE_MS = 1000

const state = ref<'idle' | 'opening' | 'closing'>('idle')
const seq = ref(0)
let openTimer: ReturnType<typeof setTimeout> | undefined
let closeTimer: ReturnType<typeof setTimeout> | undefined
let settleTimer: ReturnType<typeof setTimeout> | undefined

const clearTimers = () => {
  if (openTimer) clearTimeout(openTimer)
  if (closeTimer) clearTimeout(closeTimer)
  if (settleTimer) clearTimeout(settleTimer)
  openTimer = closeTimer = settleTimer = undefined
}

const play = (next: 'opening' | 'closing') => {
  seq.value++
  state.value = next
}

const enter = () => {
  if (closeTimer) clearTimeout(closeTimer)
  closeTimer = undefined
  if (state.value === 'opening') return
  if (openTimer) return
  openTimer = setTimeout(() => {
    openTimer = undefined
    play('opening')
  }, HOVER_GATE_MS)
}

const leave = () => {
  if (openTimer) clearTimeout(openTimer)
  openTimer = undefined
  if (state.value !== 'opening') return
  if (closeTimer) return
  closeTimer = setTimeout(() => {
    closeTimer = undefined
    play('closing')
    settleTimer = setTimeout(() => {
      settleTimer = undefined
      state.value = 'idle'
    }, CLOSING_MS)
  }, HOVER_GATE_MS)
}

defineExpose({ enter, leave })

onBeforeUnmount(clearTimers)

const src = computed(() => SOURCES[state.value])
</script>

<template>
  <!-- :key forces a fresh <img> (fresh SMIL document) per state change -->
  <img :key="seq" :src="src" class="size-full object-contain" alt="" draggable="false" />
</template>
