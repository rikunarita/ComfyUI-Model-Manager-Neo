<template>
  <Toaster
    v-bind="props"
    unstyled
    position="top-right"
    close-button
    close-button-position="top-right"
    :close-button-aria-label="closeAriaLabel"
    expand
    :visible-toasts="4"
    :gap="10"
    :offset="16"
    :mobile-offset="12"
    :duration="5000"
    :toast-options="{
      classes: {
        toast:
          'mm-toast pointer-events-auto group relative flex w-full items-start gap-3 overflow-hidden rounded-mm-card border border-mm-border p-4 pr-10',
        icon: 'mm-toast-icon mt-0.5 shrink-0',
        content: 'mm-toast-content flex min-w-0 flex-1 flex-col gap-1',
        title: 'text-sm leading-5 font-semibold text-mm-fg',
        description: 'text-xs leading-4 text-mm-muted-fg break-words',
        closeButton:
          'mm-toast-close absolute top-2.5 right-2.5 grid size-6 place-items-center rounded-full border border-mm-fg/15 bg-mm-fg/8 text-mm-muted-fg opacity-70 backdrop-blur-md transition hover:bg-mm-fg/16 hover:text-mm-fg hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none active:scale-95 group-hover:opacity-100',
        actionButton:
          'mm-transition rounded-mm-ctl border border-mm-accent/30 bg-mm-accent/18 px-3 py-1 text-xs font-medium text-mm-accent backdrop-blur-md hover:bg-mm-accent/28 active:scale-[0.97]',
        cancelButton:
          'mm-transition rounded-mm-ctl border border-mm-fg/15 bg-mm-fg/6 px-3 py-1 text-xs font-medium text-mm-fg backdrop-blur-md hover:bg-mm-fg/12 active:scale-[0.97]',
        success: 'mm-toast-success border-l-2 border-l-mm-success',
        error: 'mm-toast-error border-l-2 border-l-mm-danger',
        warning: 'mm-toast-warning border-l-2 border-l-mm-warning',
        info: 'mm-toast-info border-l-2 border-l-mm-accent',
      },
    }"
  />
</template>

<script setup lang="ts">
import { Toaster, type ToasterProps } from 'vue-sonner'
import { useI18nGlobal } from 'hooks/i18n'

const props = defineProps<ToasterProps>()

// The manual dismiss button is keyboard-reachable, so it needs a label.
const { t } = useI18nGlobal()
const closeAriaLabel = t('dismiss')
</script>
