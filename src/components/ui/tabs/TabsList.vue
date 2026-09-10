<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import { TabsList } from 'reka-ui'
import { type TabsListProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

const props = defineProps<TabsListProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <TabsList
    v-bind="delegatedProps"
    :class="
      cn(
        'inline-flex h-9 items-center justify-center rounded-mm-ctl border border-mm-fg/10 bg-mm-fg/6 p-1 text-mm-muted-fg backdrop-blur-md',
        props.class,
      )
    "
  >
    <slot />
  </TabsList>
</template>
