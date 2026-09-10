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
      classes: {
        toast:
          'mm-glass-light pointer-events-auto group flex w-full items-center gap-3 rounded-mm-ctl border border-mm-border p-4 shadow-mm-2 mm-transition hover:shadow-mm-3',
        title: 'text-sm font-medium text-mm-fg',
        description: 'text-xs text-mm-muted-fg',
        actionButton:
          'mm-transition rounded-mm-ctl border border-mm-accent/30 bg-mm-accent/18 px-3 py-1 text-xs font-medium text-mm-accent backdrop-blur-md hover:bg-mm-accent/28 active:scale-[0.97]',
        cancelButton:
          'mm-transition rounded-mm-ctl border border-mm-fg/15 bg-mm-fg/6 px-3 py-1 text-xs font-medium text-mm-fg backdrop-blur-md hover:bg-mm-fg/12 active:scale-[0.97]',
        closeButton:
          'mm-transition absolute right-2 top-2 rounded-mm-ctl border-0 bg-transparent p-1 opacity-60 hover:bg-mm-fg/10 hover:opacity-100',
        success: 'border-l-4 border-l-mm-success',
        error: 'border-l-4 border-l-mm-danger',
        warning: 'border-l-4 border-l-mm-warning',
        info: 'border-l-4 border-l-mm-accent',
      },
    }"
  />
</template>
