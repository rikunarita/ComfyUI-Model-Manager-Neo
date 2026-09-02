<script setup lang="ts">
import type { AlertDialogDescriptionProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { AlertDialogDescription } from 'reka-ui'
import { cn } from 'utils/cn'

const props = defineProps<AlertDialogDescriptionProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <AlertDialogDescription v-bind="delegatedProps" :class="cn('text-sm text-mm-muted-fg', props.class)">
    <slot />
  </AlertDialogDescription>
</template>
