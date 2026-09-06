<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { SliderRootEmits, SliderRootProps } from 'reka-ui'
import { SliderRange, SliderRoot, SliderThumb, SliderTrack, useForwardPropsEmits } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<SliderRootProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<SliderRootEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <SliderRoot
    v-bind="forwarded"
    :class="cn('relative flex w-full touch-none select-none items-center', props.class)"
  >
    <SliderTrack class="relative h-1.5 w-full grow overflow-hidden rounded-full bg-mm-surface">
      <SliderRange class="absolute h-full bg-mm-accent" />
    </SliderTrack>
    <SliderThumb
      class="mm-transition block size-4 rounded-full border-2 border-mm-accent bg-mm-bg shadow-mm-1 ring-offset-mm-bg hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mm-ring disabled:pointer-events-none disabled:opacity-50"
    />
  </SliderRoot>
</template>
