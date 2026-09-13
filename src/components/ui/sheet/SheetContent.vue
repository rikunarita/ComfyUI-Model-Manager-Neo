<script setup lang="ts">
import { X } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { DialogClose, DialogContent, DialogPortal, useForwardPropsEmits } from 'reka-ui'
import { type DialogContentEmits, type DialogContentProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'
import SheetOverlay from './SheetOverlay.vue'

interface SheetContentProps extends DialogContentProps {
  class?: HTMLAttributes['class']
  side?: 'top' | 'right' | 'bottom' | 'left'
}

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<SheetContentProps>(), { side: 'right' })
const emits = defineEmits<DialogContentEmits>()
const delegatedProps = reactiveOmit(props, 'class', 'side')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DialogPortal>
    <SheetOverlay />
    <DialogContent
      v-bind="{ ...forwarded, ...$attrs }"
      :class="
        cn(
          'mm-glass mm-scope fixed z-(--mm-z-nested-dialog) gap-4 border border-mm-border p-6 shadow-mm-3 transition ease-in-out',
          `mm-anim-sheet-${side}`,
          side === 'top' && 'inset-x-0 top-0 border-b',
          side === 'bottom' && 'inset-x-0 bottom-0 border-t',
          side === 'left' && 'inset-y-0 left-0 h-full w-3/4 border-r sm:max-w-sm',
          side === 'right' && 'inset-y-0 right-0 h-full w-3/4 border-l sm:max-w-sm',
          props.class,
        )
      "
    >
      <slot />
      <DialogClose
        class="mm-transition absolute top-4 right-4 rounded-mm-ctl border-0 bg-transparent p-1 opacity-60 hover:bg-mm-fg/10 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none"
      >
        <X class="size-4" />
        <span class="sr-only">Close</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
