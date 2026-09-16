<template>
  <!--
    Panel-scoped loading indicator.

    This used to be a viewport-sized `fixed inset-0` scrim rendered from
    App.vue (`GlobalLoading`), so every `loading.show()` — a model-list
    refresh, a save, a delete — blurred and dimmed the WHOLE ComfyUI window,
    canvas included, and sat at z-index 9999 above every dialog and popup.
    The work being waited on always belongs to one Model Manager Neo panel, so
    the overlay now lives inside that panel: GlobalDialogStack renders it into
    the topmost dialog only, `absolute inset-0` against the dialog's own
    stacking context. The host page stays visible and interactive, and the
    scrim can never cover a toast, a tooltip or the global confirm dialog.

    The caption distinguishes the first model-list load ("Loading…") from
    later refreshes ("Updating…").
  -->
  <div
    data-mm-loading
    class="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 rounded-mm-dlg bg-mm-bg/35 backdrop-blur-[3px]"
  >
    <Loader2 class="size-8 animate-spin opacity-40" />
    <span class="text-sm text-mm-muted-fg select-none">
      {{ modelsInitialized ? t('updating') : t('loading') }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { Loader2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useModels } from 'hooks/model'

const { t } = useI18n()
const { initialized } = useModels()

const modelsInitialized = initialized
</script>
