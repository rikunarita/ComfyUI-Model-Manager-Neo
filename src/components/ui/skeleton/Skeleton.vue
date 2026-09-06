<script setup lang="ts">
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

interface SkeletonProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<SkeletonProps>()
</script>

<template>
  <div :class="cn('animate-pulse rounded-mm-ctl bg-mm-surface-hover', props.class)" />
</template>
