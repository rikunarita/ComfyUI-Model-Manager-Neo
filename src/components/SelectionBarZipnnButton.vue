<script setup lang="ts">
import { computed } from 'vue'
import ZipnnProgressRing from 'components/ZipnnProgressRing.vue'
import { zipnnState } from 'hooks/zipnn'
import { assetUrl } from 'utils/media'

interface Props {
  /** Only rendered while folders are part of the selection. */
  visible: boolean
  running: boolean
  inverted: boolean
  label: string
}
const props = defineProps<Props>()

defineEmits<{ request: [] }>()

const zipnnIcon = assetUrl('zipnn-button')
/** 0-100 while a batch task runs; drives the circular ring. */
const progress = computed(() => zipnnState.progress)
</script>

<template>
  <!--
    The ZipNN artwork button of the selection bulk bar: same confirmation and
    progress behaviour as the card corner button, inverted for bundles.
  -->
  <button
    v-if="visible"
    type="button"
    class="mm-zipnn-button size-8 shrink-0 rounded-mm-ctl"
    :title="label"
    :aria-label="label"
    :disabled="props.running"
    @click="$emit('request')"
  >
    <ZipnnProgressRing v-if="props.running" :progress="progress" percent-class="text-[9px]" />
    <img
      v-else
      :src="zipnnIcon"
      alt=""
      class="size-full rounded-mm-ctl"
      :class="inverted && 'hue-rotate-180 invert'"
    />
  </button>
</template>
