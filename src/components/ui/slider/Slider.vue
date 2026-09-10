<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import { SliderRange, SliderRoot, SliderThumb, SliderTrack, useForwardPropsEmits } from 'reka-ui'
import { type SliderRootEmits, type SliderRootProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

const props = defineProps<SliderRootProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<SliderRootEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <SliderRoot
    v-bind="forwarded"
    :class="cn('relative flex w-full touch-none items-center select-none', props.class)"
  >
    <SliderTrack class="relative h-1.5 w-full grow overflow-hidden rounded-full bg-mm-fg/10">
      <SliderRange class="absolute h-full bg-mm-accent/80" />
    </SliderTrack>
    <SliderThumb
      class="mm-transition block size-4 rounded-full border border-mm-accent/50 bg-mm-bg/70 shadow-mm-accent-1 ring-offset-mm-bg backdrop-blur-md hover:scale-110 focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
    />
  </SliderRoot>
</template>
