<template>
  <table v-if="dataSource.length" class="w-full border-collapse border border-mm-border">
    <tbody>
      <tr v-for="item in dataSource" :key="item.key" class="h-8 border-b border-mm-border">
        <td class="border-r border-mm-border bg-mm-surface px-4 text-mm-muted-fg">
          {{ $t(`info.${item.key}`) }}
        </td>
        <td class="break-all px-4 text-mm-fg">{{ item.value }}</td>
      </tr>
    </tbody>
  </table>

  <div v-else class="flex flex-col items-center gap-2 py-5 text-mm-muted-fg">
    <Info class="size-5" />
    <div>no metadata</div>
  </div>
</template>

<script setup lang="ts">
import { Info } from '@lucide/vue'
import { useModelMetadata } from 'hooks/model'
import { computed } from 'vue'

const { metadata } = useModelMetadata()

const dataSource = computed(() => {
  const dataSource: { key: string; value: any }[] = []

  for (const key in metadata.value) {
    if (Object.prototype.hasOwnProperty.call(metadata.value, key)) {
      const value = metadata.value[key]
      dataSource.push({ key, value })
    }
  }

  return dataSource
})
</script>
