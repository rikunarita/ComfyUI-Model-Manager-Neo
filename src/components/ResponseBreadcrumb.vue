<template>
  <div ref="container" class="breadcrumb-container flex items-center gap-1 overflow-hidden text-sm">
    <div v-if="firstItem" class="breadcrumb-item flex items-center gap-1">
      <button
        class="mm-transition text-mm-muted-fg hover:text-mm-accent"
        @click="firstItem.command?.()"
      >
        {{ firstItem.label }}
      </button>
      <ChevronRight v-if="(items?.length ?? 0) > 1" class="size-4 shrink-0 text-mm-muted-fg" />
    </div>

    <div
      v-for="(item, index) in middleItems"
      :key="index"
      class="breadcrumb-item flex items-center gap-1"
    >
      <button
        class="mm-transition text-mm-muted-fg hover:text-mm-accent"
        @click="item.command?.()"
      >
        {{ item.label }}
      </button>
      <ChevronRight v-if="index < middleItems.length - 1 || lastItem" class="size-4 shrink-0 text-mm-muted-fg" />
    </div>

    <div v-if="lastItem" class="breadcrumb-item">
      <span class="text-mm-fg font-medium">{{ lastItem.label }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import type { BreadcrumbItem } from 'types/breadcrumb'
import { computed, ref } from 'vue'

interface Props {
  items?: BreadcrumbItem[]
}

const props = defineProps<Props>()

const container = ref<HTMLElement>()

const firstItem = computed(() => props.items?.[0])
const lastItem = computed(() => props.items?.[props.items.length - 1])
const middleItems = computed(() => {
  if (!props.items || props.items.length <= 2) return []
  return props.items.slice(1, -1)
})
</script>
