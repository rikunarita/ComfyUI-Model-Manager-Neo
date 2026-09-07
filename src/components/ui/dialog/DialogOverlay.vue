<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import { DialogOverlay } from 'reka-ui'
import { type DialogOverlayProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

const props = defineProps<DialogOverlayProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <DialogOverlay
    v-bind="delegatedProps"
    :class="
      cn(
        'fixed inset-0 z-50 animate-in bg-black/50 backdrop-blur-sm duration-200 fade-in-0',
        props.class,
      )
    "
  />
</template>
