<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'
import { badgeVariants, type BadgeVariants } from '.'

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
