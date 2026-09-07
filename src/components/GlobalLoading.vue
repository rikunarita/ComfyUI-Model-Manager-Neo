<template>
  <div v-show="loading">
    <div class="fixed top-0 left-0 size-full" style="z-index: 9999">
      <div class="flex size-full items-center justify-center bg-black/30">
        <i class="pi pi-spinner pi-spin text-3xl opacity-30"></i>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useGlobalLoading } from 'hooks/loading'

const { loading } = useGlobalLoading()
</script>
