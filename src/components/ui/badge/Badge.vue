<script setup lang="ts">
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'
import { type BadgeVariants, badgeVariants } from '.'

interface Props {
  variant?: BadgeVariants['variant']
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <div :class="cn(badgeVariants({ variant }), props.class)">
    <slot />
  </div>
</template>
