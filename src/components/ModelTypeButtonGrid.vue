<script setup lang="ts">
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'

interface TypeOption {
  label: string
  value: string
  command: () => void
}
interface Props {
  items: TypeOption[]
}
defineProps<Props>()
</script>

<template>
  <!--
    The "pick a model type" button grid of the upload dialogs (local upload
    and Hugging Face upload rendered it byte-identically).
  -->
  <div class="flex h-full flex-col overflow-hidden">
    <ResponseScroll>
      <div class="flex flex-wrap gap-4">
        <Button v-for="item in items" :key="item.value" @click="item.command">
          {{ item.label }}
        </Button>
      </div>
    </ResponseScroll>
  </div>
</template>
