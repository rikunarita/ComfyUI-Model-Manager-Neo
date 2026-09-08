<script setup lang="ts">
import { X } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { DialogClose, DialogContent, DialogPortal, useForwardPropsEmits } from 'reka-ui'
import { type DialogContentEmits, type DialogContentProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'
import DialogOverlay from './DialogOverlay.vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<
    DialogContentProps & {
      class?: HTMLAttributes['class']
      showCloseButton?: boolean
      forceMount?: boolean
      /**
       * Render the dimming/blurring overlay. Non-modal dialogs (the default
       * for the model-manager windows, matching the original PrimeVue
       * behaviour) skip it so the ComfyUI canvas stays visible & interactive.
       */
      showOverlay?: boolean
      /**
       * Inline style for the overlay. The dialog stack passes a z-index that
       * matches its window so a modal overlay correctly dims the dialogs below
       * it (the default `z-50` sits under the 2400+ dialog windows).
       */
      overlayStyle?: HTMLAttributes['style']
    }
  >(),
  { showCloseButton: true, forceMount: false, showOverlay: true },
)
const emits = defineEmits<DialogContentEmits>()
const delegatedProps = reactiveOmit(props, 'class', 'forceMount', 'showOverlay', 'overlayStyle')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DialogPortal :force-mount="forceMount">
    <DialogOverlay
      v-if="showOverlay"
      :style="overlayStyle"
      :class="forceMount && 'data-[state=closed]:hidden'"
    />
    <DialogContent
      v-bind="{ ...forwarded, ...$attrs }"
      :class="
        cn(
          'mm-glass fixed top-1/2 left-1/2 z-50 grid w-full max-w-lg -translate-1/2 gap-4 rounded-mm-dlg border border-mm-border p-6',
          'animate-in duration-200 fade-in-0 zoom-in-95',
          'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
          forceMount && 'data-[state=closed]:hidden',
          props.class,
        )
      "
    >
      <slot />
      <DialogClose
        v-if="showCloseButton"
        class="mm-transition absolute top-4 right-4 rounded-mm-ctl p-1 opacity-60 hover:bg-mm-surface-hover hover:opacity-100 focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none"
      >
        <X class="size-4" />
        <span class="sr-only">Close</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
