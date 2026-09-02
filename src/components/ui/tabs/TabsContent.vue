<script setup lang="ts">
import type { TabsContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { TabsContent } from 'reka-ui'
import { cn } from 'utils/cn'

const props = defineProps<TabsContentProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <TabsContent
    v-bind="delegatedProps"
    :class="cn(
      'mm-transition mt-2 ring-offset-mm-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mm-ring',
      props.class,
    )"
  >
    <slot />
  </TabsContent>
</template>
