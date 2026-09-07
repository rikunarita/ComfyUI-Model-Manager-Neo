<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import { ProgressIndicator, ProgressRoot } from 'reka-ui'
import { type ProgressRootProps } from 'reka-ui'
import { computed, type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

const props = withDefaults(
  defineProps<
    ProgressRootProps & {
      class?: HTMLAttributes['class']
      /**
       * `indeterminate` renders a looping sweep animation and ignores the
       * value. Parity with the PrimeVue Progress this component replaced
       * (`<Progress mode="indeterminate">`). A `null`/`undefined` modelValue
       * is treated as indeterminate too (reka-ui semantics).
       */
      mode?: 'determinate' | 'indeterminate'
    }
  >(),
  { mode: 'determinate' },
)

const isIndeterminate = computed(
  () =>
    props.mode === 'indeterminate' || props.modelValue === null || props.modelValue === undefined,
)

const delegatedProps = reactiveOmit(props, 'class', 'mode')
</script>

<template>
  <ProgressRoot
    v-bind="delegatedProps"
    :model-value="isIndeterminate ? null : props.modelValue"
    :class="cn('relative h-2 w-full overflow-hidden rounded-full bg-mm-surface', props.class)"
  >
    <ProgressIndicator
      v-if="isIndeterminate"
      class="mm-indeterminate h-full w-1/3 rounded-full bg-mm-accent"
    />
    <ProgressIndicator
      v-else
      class="mm-transition size-full flex-1 bg-mm-accent"
      :style="`transform: translateX(-${100 - (props.modelValue ?? 0)}%);`"
    />
  </ProgressRoot>
</template>
