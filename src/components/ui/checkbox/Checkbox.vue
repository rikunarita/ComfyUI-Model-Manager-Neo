<script setup lang="ts">
import type { CheckboxRootEmits, CheckboxRootProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { Check } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from 'reka-ui'
import { cn } from 'utils/cn'

const props = defineProps<CheckboxRootProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<CheckboxRootEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <CheckboxRoot
    v-bind="forwarded"
    :class="cn(
      'peer size-4 shrink-0 rounded-sm border border-mm-border-strong shadow-mm-1 mm-transition',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mm-ring',
      'disabled:cursor-not-allowed disabled:opacity-50',
      'data-[state=checked]:bg-mm-accent data-[state=checked]:text-mm-accent-fg data-[state=checked]:border-mm-accent',
      props.class,
    )"
  >
    <CheckboxIndicator class="flex items-center justify-center text-current">
      <slot>
        <Check class="size-3" />
      </slot>
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
