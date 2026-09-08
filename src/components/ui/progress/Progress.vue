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

const maxValue = computed(() => (typeof props.max === 'number' && props.max > 0 ? props.max : 100))

/**
 * reka-ui's ProgressRoot only accepts a value in `[0, max]` (or null/undefined
 * for indeterminate); anything else logs a console warning and resets to null.
 * Callers pass sentinels such as `-1` ("nothing to scan yet"), so clamp the
 * value into range and treat non-finite input as indeterminate.
 */
const numericValue = computed<number | null>(() => {
  const v = props.modelValue
  if (typeof v !== 'number' || !Number.isFinite(v)) return null
  return Math.min(Math.max(v, 0), maxValue.value)
})

const isIndeterminate = computed(
  () => props.mode === 'indeterminate' || numericValue.value === null,
)

// `modelValue` is bound explicitly below (sanitized), so omit the raw prop.
const delegatedProps = reactiveOmit(props, 'class', 'mode', 'modelValue')
</script>

<template>
  <ProgressRoot
    v-bind="delegatedProps"
    :model-value="isIndeterminate ? null : numericValue"
    :class="cn('relative h-2 w-full overflow-hidden rounded-full bg-mm-surface', props.class)"
  >
    <ProgressIndicator
      v-if="isIndeterminate"
      class="mm-indeterminate h-full w-1/3 rounded-full bg-mm-accent"
    />
    <ProgressIndicator
      v-else
      class="mm-transition size-full flex-1 bg-mm-accent"
      :style="`transform: translateX(-${100 - (numericValue ?? 0)}%);`"
    />
  </ProgressRoot>
</template>
