<script setup lang="ts">
import { TreeItem } from 'reka-ui'
import TreeItemContent from './TreeItemContent.vue'

interface Props {
  item: any
}
defineProps<Props>()
</script>

<template>
  <!--
    One tree item plus its row content. The virtual and the non-virtual
    branch of Tree.vue rendered this block byte-identically, so it lives
    here once; the label fallback stays reachable for consumers that do not
    provide an `item` slot.
  -->
  <TreeItem
    v-slot="{ isExpanded, isSelected }"
    v-bind="item.bind"
    :value="item.value"
    :level="item.level"
  >
    <TreeItemContent
      :item="item"
      :is-expanded="isExpanded"
      :is-selected="isSelected as any"
      :has-children="!!item.hasChildren"
      :level="item.level"
    >
      <template #item="row">
        <slot name="item" :item="row.item">
          <span class="overflow-hidden text-ellipsis">{{ row.item?.value?.label }}</span>
        </slot>
      </template>
    </TreeItemContent>
  </TreeItem>
</template>
