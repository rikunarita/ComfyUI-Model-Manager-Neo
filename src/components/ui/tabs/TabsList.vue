<script setup lang="ts">
import type { TabsListProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { TabsList } from 'reka-ui'
import { cn } from 'utils/cn'

const props = defineProps<TabsListProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <TabsList
    v-bind="delegatedProps"
    :class="cn(
      'inline-flex h-9 items-center justify-center rounded-mm-ctl bg-mm-surface p-1 text-mm-muted-fg',
      props.class,
    )"
  >
    <slot />
  </TabsList>
</template>
