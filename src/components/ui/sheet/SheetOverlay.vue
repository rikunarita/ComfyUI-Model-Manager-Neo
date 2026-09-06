<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DialogOverlayProps } from 'reka-ui'
import { DialogOverlay } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<DialogOverlayProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <DialogOverlay
    v-bind="delegatedProps"
    :class="cn('fixed inset-0 z-50 bg-black/50 backdrop-blur-sm animate-in fade-in-0 duration-300', props.class)"
  />
</template>
