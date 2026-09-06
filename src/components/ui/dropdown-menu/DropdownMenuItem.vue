<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DropdownMenuItemProps } from 'reka-ui'
import { DropdownMenuItem, useForwardProps } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<
  DropdownMenuItemProps & { class?: HTMLAttributes['class']; inset?: boolean }
>()
const delegatedProps = reactiveOmit(props, 'class', 'inset')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <DropdownMenuItem
    v-bind="forwardedProps"
    :class="cn(
      'mm-transition relative flex cursor-default select-none items-center gap-2 rounded-mm-ctl px-2 py-1.5 text-sm outline-none',
      'hover:bg-mm-surface-hover focus:bg-mm-surface-hover',
      'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      '[&>svg]:size-4 [&>svg]:shrink-0',
      inset && 'pl-8',
      props.class,
    )"
  >
    <slot />
  </DropdownMenuItem>
</template>
