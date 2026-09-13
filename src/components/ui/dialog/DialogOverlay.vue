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
        'mm-anim-fade fixed inset-0 z-(--mm-z-nested-overlay) bg-black/50 backdrop-blur-sm',
        props.class,
      )
    "
  />
</template>
