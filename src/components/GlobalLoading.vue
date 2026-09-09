<template>
  <div v-show="loading">
    <div class="fixed top-0 left-0 size-full" style="z-index: 9999">
      <div class="flex size-full items-center justify-center bg-black/30">
        <!--
          BUG FIX: this was `<i class="pi pi-spinner pi-spin text-3xl opacity-30">`.
          PrimeVue/PrimeIcons was removed from the fork, so no `.pi-*` rule (and
          no icon font) exists any more — the element rendered as an empty box
          and the global loading overlay showed a dark scrim with NO spinner.
          Long operations (model list refresh, downloads, uploads) therefore
          gave the user no feedback at all. Swapped for the Lucide spinner the
          rest of the UI already uses; `animate-spin` replaces `pi-spin`.
        -->
        <Loader2 class="size-8 animate-spin opacity-30" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loader2 } from '@lucide/vue'
import { useGlobalLoading } from 'hooks/loading'

const { loading } = useGlobalLoading()
</script>
