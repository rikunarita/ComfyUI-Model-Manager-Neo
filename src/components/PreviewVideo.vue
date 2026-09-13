<template>
  <video
    class="size-full object-cover"
    playsinline
    autoplay
    loop
    muted
    disablepictureinpicture
    :preload="preload"
  >
    <!--
      Optimization B-4: the same URL used to be declared twice (as mp4 AND as
      webm), so a .webm preview first failed a MIME check and logged a media
      error before falling back. One source with the type derived from the URL
      is enough - unknown extensions let the browser sniff.
    -->
    <source v-if="mimeType" :src="src" :type="mimeType" />
    <source v-else :src="src" />
  </video>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  src: string
  preload?: 'none' | 'metadata' | 'auto'
}

const props = withDefaults(defineProps<Props>(), {
  preload: 'metadata',
})

const MIME: Record<string, string> = {
  mp4: 'video/mp4',
  webm: 'video/webm',
  mov: 'video/quicktime',
  avi: 'video/x-msvideo',
  mkv: 'video/x-matroska',
  m4v: 'video/x-m4v',
  ogv: 'video/ogg',
}

const mimeType = computed(() => {
  const path = props.src.split('?')[0].split('#')[0].toLowerCase()
  const ext = path.slice(path.lastIndexOf('.') + 1)
  return MIME[ext] ?? ''
})
</script>
