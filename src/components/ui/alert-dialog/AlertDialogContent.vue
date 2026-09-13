<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import {
  AlertDialogContent,
  AlertDialogOverlay,
  AlertDialogPortal,
  useForwardPropsEmits,
} from 'reka-ui'
import { type AlertDialogContentEmits, type AlertDialogContentProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

defineOptions({ inheritAttrs: false })

const props = defineProps<AlertDialogContentProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<AlertDialogContentEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <AlertDialogPortal>
    <AlertDialogOverlay
      class="mm-anim-fade fixed inset-0 z-(--mm-z-confirm-overlay) bg-black/50 backdrop-blur-sm"
    />
    <AlertDialogContent
      v-bind="{ ...forwarded, ...$attrs }"
      :class="
        cn(
          'mm-glass mm-scope fixed top-1/2 left-1/2 z-(--mm-z-confirm) grid w-full max-w-lg -translate-1/2 gap-4 rounded-mm-dlg border border-mm-border p-6',
          'mm-anim-pop',
          props.class,
        )
      "
    >
      <slot />
    </AlertDialogContent>
  </AlertDialogPortal>
</template>
