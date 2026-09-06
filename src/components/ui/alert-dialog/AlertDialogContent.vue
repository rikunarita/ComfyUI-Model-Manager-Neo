<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { AlertDialogContentEmits, AlertDialogContentProps } from 'reka-ui'
import {
  AlertDialogContent,
  AlertDialogOverlay,
  AlertDialogPortal,
  useForwardPropsEmits,
} from 'reka-ui'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps<AlertDialogContentProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<AlertDialogContentEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <AlertDialogPortal>
    <AlertDialogOverlay
      class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm animate-in fade-in-0 duration-200"
    />
    <AlertDialogContent
      v-bind="{ ...forwarded, ...$attrs }"
      :class="cn(
        'mm-glass fixed left-1/2 top-1/2 z-50 grid w-full max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 rounded-mm-dlg border border-mm-border p-6',
        'animate-in fade-in-0 zoom-in-95 duration-200',
        'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
        props.class,
      )"
    >
      <slot />
    </AlertDialogContent>
  </AlertDialogPortal>
</template>
