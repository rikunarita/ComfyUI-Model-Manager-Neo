<script setup lang="ts">
import type { TabsTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { TabsTrigger, useForwardProps } from 'reka-ui'
import { cn } from 'utils/cn'

const props = defineProps<TabsTriggerProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <TabsTrigger
    v-bind="forwardedProps"
    :class="cn(
      'mm-transition inline-flex items-center justify-center whitespace-nowrap rounded-mm-ctl px-3 py-1 text-sm font-medium ring-offset-mm-bg',
      'hover:bg-mm-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mm-ring',
      'disabled:pointer-events-none disabled:opacity-50',
      'data-[state=active]:bg-mm-bg data-[state=active]:text-mm-fg data-[state=active]:shadow-mm-1',
      props.class,
    )"
  >
    <slot />
  </TabsTrigger>
</template>
