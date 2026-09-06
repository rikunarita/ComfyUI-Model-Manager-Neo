<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { AlertDialogTitleProps } from 'reka-ui'
import { AlertDialogTitle } from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

const props = defineProps<AlertDialogTitleProps & { class?: HTMLAttributes['class'] }>()
const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <AlertDialogTitle v-bind="delegatedProps" :class="cn('text-lg font-semibold', props.class)">
    <slot />
  </AlertDialogTitle>
</template>
