<script setup lang="ts">
import { type InformationRow } from 'utils/modelInformation'

interface Props {
  row: InformationRow
}
defineProps<Props>()
</script>

<template>
  <!-- The value cell of the Information table: link list, link, or text. -->
  <div v-if="row.kind === 'links'" class="flex flex-col gap-1 py-1">
    <a
      v-for="(url, index) in row.values"
      :key="`${url}-${index}`"
      :href="url"
      target="_blank"
      rel="noopener noreferrer"
      class="text-mm-accent hover:underline"
      >{{ url }}</a
    >
  </div>
  <a
    v-else-if="row.kind === 'link'"
    :href="row.value"
    target="_blank"
    rel="noopener noreferrer"
    class="text-mm-accent hover:underline"
    >{{ row.value }}</a
  >
  <span v-else>{{ row.value }}</span>
</template>
