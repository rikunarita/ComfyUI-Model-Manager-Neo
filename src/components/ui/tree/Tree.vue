<script setup lang="ts" generic="T extends Record<string, any>">
import { TreeRoot, TreeVirtualizer } from 'reka-ui'
import { type FlattenedItem } from 'reka-ui'
import { cn } from 'utils/cn'
import TreeBranch from './TreeBranch.vue'

interface Props {
  items: T[]
  getKey: (item: T) => string
  getChildren?: (item: T) => T[] | undefined
  virtual?: boolean
  estimateSize?: number
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  virtual: false,
  estimateSize: 28,
})

const model = defineModel<T | T[]>()
const expanded = defineModel<string[]>('expanded', { default: () => [] })

interface TreeSlotProps {
  flattenItems: FlattenedItem<T>[]
}
</script>

<template>
  <TreeRoot
    v-model="model as any"
    v-model:expanded="expanded"
    :items="items"
    :get-key="getKey"
    :get-children="getChildren"
    :class="cn('space-y-0.5', props.class)"
  >
    <!-- Virtual mode -->
    <TreeVirtualizer
      v-if="virtual"
      v-slot="{ item }"
      :estimate-size="estimateSize"
      :text-content="(opt: any) => getKey(opt)"
    >
      <TreeBranch :item="item">
        <template v-if="$slots.item" #item="row">
          <slot name="item" :item="row.item" />
        </template>
      </TreeBranch>
    </TreeVirtualizer>

    <!-- Non-virtual mode -->
    <template v-if="!virtual" #default="slotProps">
      <TreeBranch
        v-for="item in (slotProps as TreeSlotProps).flattenItems"
        :key="item._id"
        :item="item"
      >
        <template v-if="$slots.item" #item="row">
          <slot name="item" :item="row.item" />
        </template>
      </TreeBranch>
    </template>
  </TreeRoot>
</template>
