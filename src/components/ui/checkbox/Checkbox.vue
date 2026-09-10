<script setup lang="ts">
import { Check } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from 'reka-ui'
import { type CheckboxRootEmits, type CheckboxRootProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

const props = defineProps<CheckboxRootProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<CheckboxRootEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <CheckboxRoot
    v-bind="forwarded"
    :class="
      cn(
        'peer mm-transition size-4 shrink-0 rounded-sm border border-mm-fg/20 bg-mm-fg/6 shadow-mm-glass-1 backdrop-blur-sm',
        'focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'data-[state=checked]:border-mm-accent/50 data-[state=checked]:bg-mm-accent/30 data-[state=checked]:text-mm-accent',
        props.class,
      )
    "
  >
    <CheckboxIndicator class="flex items-center justify-center text-current">
      <slot>
        <Check class="size-3" />
      </slot>
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
