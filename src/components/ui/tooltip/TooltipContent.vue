<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import { TooltipArrow, TooltipContent, TooltipPortal, useForwardPropsEmits } from 'reka-ui'
import { type TooltipContentEmits, type TooltipContentProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<TooltipContentProps & { class?: HTMLAttributes['class'] }>(),
  { sideOffset: 4 },
)
const emits = defineEmits<TooltipContentEmits>()
const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <TooltipPortal>
    <TooltipContent
      v-bind="{ ...forwarded, ...$attrs }"
      :class="
        cn(
          'mm-glass-light mm-scope z-(--mm-z-popover) overflow-hidden rounded-mm-ctl border border-mm-border px-3 py-1.5 text-xs text-mm-fg shadow-mm-2',
          'mm-anim-menu',
          props.class,
        )
      "
    >
      <slot />
      <TooltipArrow class="fill-mm-bg" />
    </TooltipContent>
  </TooltipPortal>
</template>
