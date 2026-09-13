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
  -->
  <div
    data-mm-loading
    class="absolute inset-0 z-30 flex items-center justify-center rounded-mm-dlg bg-mm-bg/35 backdrop-blur-[3px]"
  >
    <Loader2 class="size-8 animate-spin opacity-40" />
  </div>
</template>

<script setup lang="ts">
import { Loader2 } from '@lucide/vue'
</script>
