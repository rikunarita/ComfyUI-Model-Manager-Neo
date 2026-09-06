<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { SelectSeparatorProps } from 'reka-ui'
import { SelectSeparator } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<SelectSeparatorProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <SelectSeparator
    v-bind="delegatedProps"
    :class="cn('-mx-1 my-1 h-px bg-mm-border', props.class)"
  />
</template>
