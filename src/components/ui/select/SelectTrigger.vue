<script setup lang="ts">
import { ChevronDown } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { SelectTriggerProps } from 'reka-ui'
import { SelectIcon, SelectTrigger, useForwardProps } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = withDefaults(
  defineProps<SelectTriggerProps & { class?: HTMLAttributes['class']; size?: 'sm' | 'default' }>(),
  { size: 'default' },
)
const delegatedProps = reactiveOmit(props, 'class', 'size')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <SelectTrigger
    v-bind="forwardedProps"
    :class="cn(
      'mm-transition flex h-9 w-full items-center justify-between gap-2 rounded-mm-ctl border border-mm-border-strong bg-mm-surface px-3 py-2 text-sm shadow-mm-1',
      'placeholder:text-mm-muted-fg hover:border-mm-accent/60',
      'focus:outline-none focus:ring-2 focus:ring-mm-ring focus:border-mm-accent',
      'disabled:cursor-not-allowed disabled:opacity-50',
      '[&>span]:line-clamp-1',
      props.size === 'sm' && 'h-8 text-xs',
      props.class,
    )"
  >
    <slot />
    <SelectIcon as-child>
      <ChevronDown class="size-4 opacity-50 mm-transition" />
    </SelectIcon>
  </SelectTrigger>
</template>
