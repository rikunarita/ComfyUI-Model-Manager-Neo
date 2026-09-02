<script setup lang="ts">
import { Toaster, type ToasterProps } from 'vue-sonner'

const props = defineProps<ToasterProps>()
</script>

<template>
  <Toaster
    v-bind="props"
    unstyled
    position="top-right"
    :toast-options="{
      classNames: {
        toast: 'mm-glass-light pointer-events-auto group flex w-full items-center gap-3 rounded-mm-ctl border border-mm-border p-4 shadow-mm-2 mm-transition hover:shadow-mm-3',
        title: 'text-sm font-medium text-mm-fg',
        description: 'text-xs text-mm-muted-fg',
        actionButton: 'mm-transition rounded-mm-ctl bg-mm-accent px-3 py-1 text-xs font-medium text-mm-accent-fg hover:brightness-110 active:scale-[0.97]',
        cancelButton: 'mm-transition rounded-mm-ctl border border-mm-border-strong px-3 py-1 text-xs font-medium hover:bg-mm-surface-hover active:scale-[0.97]',
        closeButton: 'mm-transition absolute right-2 top-2 rounded-mm-ctl p-1 opacity-60 hover:opacity-100 hover:bg-mm-surface-hover',
        success: 'border-l-4 border-l-mm-success',
        error: 'border-l-4 border-l-mm-danger',
        warning: 'border-l-4 border-l-mm-accent',
        info: 'border-l-4 border-l-mm-accent',
      },
    }"
  />
</template>
