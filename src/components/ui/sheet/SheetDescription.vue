<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DialogDescriptionProps } from 'reka-ui'
import { DialogDescription } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<DialogDescriptionProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <DialogDescription v-bind="delegatedProps" :class="cn('text-sm text-mm-muted-fg', props.class)">
    <slot />
  </DialogDescription>
</template>
