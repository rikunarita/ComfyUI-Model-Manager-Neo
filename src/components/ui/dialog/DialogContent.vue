<script setup lang="ts">
import type { DialogContentEmits, DialogContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { X } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import {
  DialogClose,
  DialogContent,
  DialogPortal,
  useForwardPropsEmits,
} from 'reka-ui'
import { cn } from 'utils/cn'
import DialogOverlay from './DialogOverlay.vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<DialogContentProps & { class?: HTMLAttributes['class']; showCloseButton?: boolean }>(),
  { showCloseButton: true },
)
const emits = defineEmits<DialogContentEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DialogPortal>
    <DialogOverlay />
    <DialogContent
      v-bind="{ ...forwarded, ...$attrs }"
      :class="cn(
        'mm-glass fixed left-1/2 top-1/2 z-50 grid w-full max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 rounded-mm-dlg border border-mm-border p-6',
        'animate-in fade-in-0 zoom-in-95 duration-200',
        'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
        props.class,
      )"
    >
      <slot />
      <DialogClose
        v-if="showCloseButton"
        class="mm-transition absolute right-4 top-4 rounded-mm-ctl p-1 opacity-60 hover:opacity-100 hover:bg-mm-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mm-ring"
      >
        <X class="size-4" />
        <span class="sr-only">Close</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
