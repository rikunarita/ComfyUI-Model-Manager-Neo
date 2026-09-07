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
    <SliderTrack class="relative h-1.5 w-full grow overflow-hidden rounded-full bg-mm-surface">
      <SliderRange class="absolute h-full bg-mm-accent" />
    </SliderTrack>
    <SliderThumb
      class="mm-transition block size-4 rounded-full border-2 border-mm-accent bg-mm-bg shadow-mm-1 ring-offset-mm-bg hover:scale-110 focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
    />
  </SliderRoot>
</template>
