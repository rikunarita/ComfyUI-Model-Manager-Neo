<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { cn } from 'utils/cn'

interface Props {
  isExpanded: boolean
  isSelected: boolean
  hasChildren: boolean
  level: number
  class?: string
}

const props = defineProps<Props>()
</script>

<template>
  <div
    :class="cn(
      'mm-transition group flex h-7 items-center gap-1 rounded-mm-ctl px-2 text-sm cursor-default',
      'hover:bg-mm-surface-hover',
      isSelected && 'bg-mm-surface-selected text-mm-accent',
      props.class,
    )"
    :style="{ paddingLeft: `${level * 16 + 8}px` }"
  >
    <ChevronRight
      v-if="hasChildren"
      :class="cn(
        'size-4 shrink-0 mm-transition text-mm-muted-fg',
        isExpanded && 'rotate-90',
      )"
    />
    <span v-else class="size-4 shrink-0" />
    <slot />
  </div>
</template>
