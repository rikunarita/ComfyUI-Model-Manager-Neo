<template>
  <div
    class="rounded-mm-card border-2 border-dashed border-mm-border p-4 text-mm-muted-fg mm-transition cursor-pointer"
    :class="{
      'border-mm-accent bg-mm-surface-hover ring-2 ring-mm-ring/30': isDragOver,
      'hover:border-mm-accent/60 hover:bg-mm-surface-hover': !isDragOver,
    }"
    @dragenter.stop.prevent="isDragOver = true"
    @dragover.stop.prevent="isDragOver = true"
    @dragleave.stop.prevent="isDragOver = false"
    @drop.stop.prevent="handleDropFile"
    @click="handleClick"
  >
    <slot name="default">
      <div class="flex h-full flex-col items-center justify-center gap-2">
        <UploadCloud class="size-8 text-mm-accent" />
        <p class="m-0 select-none overflow-hidden text-ellipsis text-sm">
          {{ $t('uploadFile') }}
        </p>
      </div>
    </slot>
  </div>
</template>

<script setup lang="ts">
import { UploadCloud } from '@lucide/vue'
import type { SelectEvent, SelectFile } from 'types/typings'
import { ref } from 'vue'

const emits = defineEmits<{
  select: [event: SelectEvent]
}>()

const isDragOver = ref(false)

const convertFileList = (fileList: FileList) => {
  const files: SelectFile[] = []
  for (const file of fileList) {
    const selectFile = file as SelectFile
    selectFile.objectURL = URL.createObjectURL(file)
    files.push(selectFile)
  }
  return files
}

const handleDropFile = (event: DragEvent) => {
  isDragOver.value = false
  const files = event.dataTransfer?.files

  if (files) {
    emits('select', { originalEvent: event, files: convertFileList(files) })
  }
}

const handleClick = (event: MouseEvent) => {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,video/*'
  input.onchange = () => {
    const files = input.files
    if (files) {
      emits('select', { originalEvent: event, files: convertFileList(files) })
    }
  }
  input.click()
}
</script>
