<script setup lang="ts">
import type { SelectLabelProps } from 'reka-ui'
import { SelectLabel } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<SelectLabelProps & { class?: HTMLAttributes['class'] }>()
</script>

<template>
  <SelectLabel :class="cn('px-2 py-1.5 text-sm font-semibold', props.class)">
    <slot />
  </SelectLabel>
</template>
