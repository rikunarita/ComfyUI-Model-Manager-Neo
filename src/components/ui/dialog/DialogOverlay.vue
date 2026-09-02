<script setup lang="ts">
import type { DialogOverlayProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { DialogOverlay } from 'reka-ui'
import { cn } from 'utils/cn'

const props = defineProps<DialogOverlayProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <DialogOverlay
    v-bind="delegatedProps"
    :class="cn(
      'fixed inset-0 z-50 bg-black/50 backdrop-blur-sm animate-in fade-in-0 duration-200',
      props.class,
    )"
  />
</template>
