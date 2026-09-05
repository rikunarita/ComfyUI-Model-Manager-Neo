<template>
  <div
    ref="container"
    class="breadcrumb-container flex items-center gap-1 overflow-hidden text-sm"
  >
    <template v-for="(item, index) in items" :key="index">
      <button
        v-if="index < items.length - 1"
        class="mm-transition text-mm-muted-fg hover:text-mm-accent"
        @click="item.command?.()"
      >
        {{ item.label }}
      </button>
      <span v-else class="font-medium text-mm-fg">{{ item.label }}</span>
      <ChevronRight
        v-if="index < items.length - 1"
        class="size-4 shrink-0 text-mm-muted-fg"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import type { BreadcrumbItem } from 'types/breadcrumb'
import { ref } from 'vue'

interface Props {
  items?: BreadcrumbItem[]
}

defineProps<Props>()

const container = ref<HTMLElement>()
</script>
