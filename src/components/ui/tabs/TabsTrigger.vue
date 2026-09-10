<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import { TabsTrigger, useForwardProps } from 'reka-ui'
import { type TabsTriggerProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

const props = defineProps<TabsTriggerProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <TabsTrigger
    v-bind="forwardedProps"
    :class="
      cn(
        'mm-transition inline-flex items-center justify-center rounded-mm-ctl border border-transparent px-3 py-1 text-sm font-medium whitespace-nowrap ring-offset-mm-bg',
        'hover:bg-mm-fg/8 hover:text-mm-fg focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none',
        'disabled:pointer-events-none disabled:opacity-50',
        'data-[state=active]:border-mm-accent/30 data-[state=active]:bg-mm-accent/16 data-[state=active]:text-mm-accent data-[state=active]:shadow-mm-accent-1 data-[state=active]:backdrop-blur-md',
        props.class,
      )
    "
  >
    <slot />
  </TabsTrigger>
</template>
