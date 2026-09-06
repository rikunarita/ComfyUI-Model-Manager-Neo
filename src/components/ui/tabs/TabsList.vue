<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { TabsListProps } from 'reka-ui'
import { TabsList } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

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
