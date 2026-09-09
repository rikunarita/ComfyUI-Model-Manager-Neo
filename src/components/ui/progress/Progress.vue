<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import { ProgressIndicator, ProgressRoot } from 'reka-ui'
import { type ProgressRootProps } from 'reka-ui'
import { computed, type HTMLAttributes, useSlots } from 'vue'
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

const slots = useSlots()

/**
 * BUG FIX: the default slot was never rendered, so any label passed to this
 * component was silently dropped — and because the indicator is translated
 * fully out of view at 0%, a bar with no label looked completely empty. The
 * PrimeVue ProgressBar this component replaced renders
 * `<slot>{{ value + '%' }}</slot>` inside its label, so the slot is part of the
 * contract callers can rely on.
 *
 * The label is drawn as an overlay centred on the bar instead of inside it:
 * reka-ui's root needs `overflow-hidden` to clip the sliding indicator, which
 * would also clip the text on such a thin track.
 */
const hasLabel = computed(() => !!slots.default)

const maxValue = computed(() => (typeof props.max === 'number' && props.max > 0 ? props.max : 100))

/**
 * reka-ui's ProgressRoot only accepts a value in `[0, max]` (or null/undefined
 * for indeterminate); anything else logs a console warning and resets to null.
 * Callers may pass out-of-range sentinels (e.g. `-1` for "nothing to show
 * yet"), so clamp the value into range and treat non-finite input as
 * indeterminate.
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
  <div class="relative w-full">
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

    <div
      v-if="hasLabel"
      class="text-shadow pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 text-center text-xs leading-none font-medium text-mm-fg"
    >
      <slot />
    </div>
  </div>
</template>
