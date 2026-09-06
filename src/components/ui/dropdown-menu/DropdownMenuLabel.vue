<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DropdownMenuLabelProps } from 'reka-ui'
import { DropdownMenuLabel } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<
  DropdownMenuLabelProps & { class?: HTMLAttributes['class']; inset?: boolean }
>()
const delegatedProps = reactiveOmit(props, 'class', 'inset')
</script>

<template>
  <DropdownMenuLabel
    v-bind="delegatedProps"
    :class="cn('px-2 py-1.5 text-sm font-semibold', inset && 'pl-8', props.class)"
  >
    <slot />
  </DropdownMenuLabel>
</template>
