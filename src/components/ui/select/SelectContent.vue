<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { SelectContentEmits, SelectContentProps } from 'reka-ui'
import { SelectContent, SelectPortal, SelectViewport, useForwardPropsEmits } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'
import { SelectScrollDownButton, SelectScrollUpButton } from '.'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<SelectContentProps & { class?: HTMLAttributes['class'] }>(),
  { position: 'popper' },
)
const emits = defineEmits<SelectContentEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <SelectPortal>
    <SelectContent
      v-bind="{ ...forwarded, ...$attrs }"
      :class="cn(
        'mm-glass-light relative z-50 max-h-96 min-w-[8rem] overflow-hidden rounded-mm-ctl border border-mm-border shadow-mm-2',
        'animate-in fade-in-0 zoom-in-95 duration-160',
        'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
        position === 'popper' && 'data-[side=bottom]:translate-y-1 data-[side=top]:-translate-y-1',
        props.class,
      )"
    >
      <SelectScrollUpButton />
      <SelectViewport
        :class="cn(
          'p-1',
          position === 'popper' && 'h-[var(--reka-select-trigger-height)] w-full min-w-[var(--reka-select-trigger-width)]',
        )"
      >
        <slot />
      </SelectViewport>
      <SelectScrollDownButton />
    </SelectContent>
  </SelectPortal>
</template>
