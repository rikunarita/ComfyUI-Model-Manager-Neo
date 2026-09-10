<script setup lang="ts">
import { useVModel } from '@vueuse/core'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

const props = defineProps<{
  defaultValue?: string | number
  modelValue?: string | number
  class?: HTMLAttributes['class']
}>()

const emits = defineEmits<(e: 'update:modelValue', payload: string | number) => void>()

const modelValue = useVModel(props, 'modelValue', emits, {
  passive: true,
  defaultValue: props.defaultValue,
})
</script>

<template>
  <input
    v-model="modelValue"
    :class="
      cn(
        'mm-transition flex h-9 w-full rounded-mm-ctl border border-mm-fg/12 bg-mm-fg/6 px-3 py-1 text-sm shadow-mm-glass-1 backdrop-blur-md',
        'placeholder:text-mm-muted-fg hover:border-mm-accent/60',
        'focus-visible:border-mm-accent focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        props.class,
      )
    "
  />
</template>
