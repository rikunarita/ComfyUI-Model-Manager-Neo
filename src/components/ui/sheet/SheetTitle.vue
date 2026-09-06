<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DialogTitleProps } from 'reka-ui'
import { DialogTitle } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<DialogTitleProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <DialogTitle v-bind="delegatedProps" :class="cn('text-lg font-semibold text-mm-fg', props.class)">
    <slot />
  </DialogTitle>
</template>
