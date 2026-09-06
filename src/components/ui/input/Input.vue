<script setup lang="ts">
import { useVModel } from '@vueuse/core'
import { cn } from 'utils/cn'
import type { HTMLAttributes } from 'vue'

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
    :class="cn(
      'mm-transition flex h-9 w-full rounded-mm-ctl border border-mm-border-strong bg-mm-surface px-3 py-1 text-sm shadow-mm-1',
      'placeholder:text-mm-muted-fg hover:border-mm-accent/60',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:border-mm-accent',
      'disabled:cursor-not-allowed disabled:opacity-50',
      props.class,
    )"
  />
</template>
