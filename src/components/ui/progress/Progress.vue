<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { ProgressRootProps } from 'reka-ui'
import { ProgressIndicator, ProgressRoot } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = withDefaults(defineProps<ProgressRootProps & { class?: HTMLAttributes['class'] }>(), {
  modelValue: 0,
})
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <ProgressRoot
    v-bind="delegatedProps"
    :class="cn('relative h-2 w-full overflow-hidden rounded-full bg-mm-surface', props.class)"
  >
    <ProgressIndicator
      class="mm-transition h-full w-full flex-1 bg-mm-accent"
      :style="`transform: translateX(-${100 - (props.modelValue ?? 0)}%);`"
    />
  </ProgressRoot>
</template>
