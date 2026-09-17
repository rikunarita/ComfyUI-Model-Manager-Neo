<script setup lang="ts">
import TreeRow from './TreeRow.vue'

interface Props {
  item: any
  isExpanded: boolean
  isSelected: boolean
  hasChildren: boolean
  level: number
}
defineProps<Props>()
</script>

<template>
  <!--
    One tree row plus the pass-through `item` slot. The virtual and the
    non-virtual branch of Tree.vue rendered this block byte-identically, so
    it lives here once.
  -->
  <TreeRow
    :is-expanded="isExpanded"
    :is-selected="isSelected as any"
    :has-children="hasChildren"
    :level="level"
  >
    <slot name="item" :item="item">
      <span class="overflow-hidden text-ellipsis">{{ item?.value?.label }}</span>
    </slot>
  </TreeRow>
</template>
