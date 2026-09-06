<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { AlertDialogDescriptionProps } from 'reka-ui'
import { AlertDialogDescription } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<AlertDialogDescriptionProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <AlertDialogDescription
    v-bind="delegatedProps"
    :class="cn('text-sm text-mm-muted-fg', props.class)"
  >
    <slot />
  </AlertDialogDescription>
</template>
