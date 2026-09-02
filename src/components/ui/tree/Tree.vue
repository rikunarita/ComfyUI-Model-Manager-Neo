<script setup lang="ts" generic="T extends Record<string, any>">
import { TreeItem, TreeRoot, TreeVirtualizer } from 'reka-ui'
import { cn } from 'utils/cn'
import TreeRow from './TreeRow.vue'

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
    <template v-if="virtual">
      <TreeVirtualizer
        v-slot="{ item }"
        :estimate-size="estimateSize"
        :text-content="(opt: any) => getKey(opt)"
      >
        <TreeItem
          v-bind="item.bind"
          v-slot="{ isExpanded, isSelected }"
          as-child
          :value="item.value"
          :level="item.level"
        >
          <TreeRow
            :is-expanded="isExpanded"
            :is-selected="isSelected as any"
            :has-children="!!item.hasChildren"
            :level="item.level"
          >
            <slot name="item" :item="item" />
          </TreeRow>
        </TreeItem>
      </TreeVirtualizer>
    </template>
    <template v-else="{ flattenItems }">
      <TreeItem
        v-for="item in flattenItems"
        :key="item._id"
        v-bind="item.bind"
        v-slot="{ isExpanded, isSelected }"
        as-child
        :value="item.value"
        :level="item.level"
      >
        <TreeRow
          :is-expanded="isExpanded"
          :is-selected="isSelected as any"
          :has-children="!!item.hasChildren"
          :level="item.level"
        >
          <slot name="item" :item="item" />
        </TreeRow>
      </TreeItem>
    </template>
  </TreeRoot>
</template>
