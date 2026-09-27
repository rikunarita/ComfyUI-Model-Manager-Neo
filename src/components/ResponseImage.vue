<template>
  <span class="relative">
    <!-- C4 (Plan §4.8): decode off the main thread - the grid re-renders
         dozens of these per scroll frame, and a synchronous decode is what
         made fast scrolling stutter. `loading="lazy"` is deliberately NOT
         set: the list is already virtualised, so every rendered image is
         on-screen by definition. -->
    <img :src="src" :alt="alt" decoding="async" v-bind="$attrs" @error="onError" />
    <img v-if="error" v-show="loadError" :src="error" decoding="async" class="absolute top-0" />
  </span>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface Props {
  src?: string
  alt?: string
  error?: string
}

const props = defineProps<Props>()

defineOptions({
  inheritAttrs: false,
})

const loadError = ref(false)

watch(
  () => props.src,
  () => {
    loadError.value = !props.src
  },
  { immediate: true },
)

const onError = () => {
  loadError.value = true
}
</script>
