<script setup lang="ts">
import { Primitive } from 'reka-ui'
import { type PrimitiveProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'
import { buttonVariants } from '.'
import { type ButtonVariants } from '.'

interface Props extends PrimitiveProps {
  variant?: ButtonVariants['variant']
  size?: ButtonVariants['size']
  class?: HTMLAttributes['class']
  /**
   * Native button type.
   *
   * BUG FIX: this defaulted to the HTML built-in `"submit"`, which is not what
   * the PrimeVue Button this component replaced did — PrimeVue injects
   * `asAttrs: { type: 'button' }` for `as="BUTTON"`. Every icon button in
   * `ModelContent`'s `<form>` therefore submitted the form on click. The
   * visible casualty: pressing the pencil ("edit") in the model-detail dialog
   * set `editable = true` and then immediately ran the submit handler, which
   * saved and set `editable = false` again — the model editor could never be
   * opened, and the transient edit state wiped `formData.type` (the
   * "Directory" row vanished and any later save sent an empty type).
   */
  type?: 'button' | 'submit' | 'reset'
}

const props = withDefaults(defineProps<Props>(), {
  as: 'button',
  type: 'button',
})
</script>

<template>
  <Primitive
    :as="as"
    :as-child="asChild"
    :type="as === 'button' ? props.type : undefined"
    :class="cn(buttonVariants({ variant, size }), props.class)"
  >
    <slot />
  </Primitive>
</template>
