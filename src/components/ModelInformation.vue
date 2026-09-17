<template>
  <div class="flex flex-col gap-6">
    <!--
      Information table: the parsed YAML front-matter of the model notes
      (author, baseModel, hashes, format/precision, model page, every preview
      URL, unknown keys verbatim at the end). Read-only by design - the notes
      themselves remain editable through the Description tab.
    -->
    <table v-if="rows.length" class="w-full border-collapse border border-mm-border">
      <tbody>
        <tr v-for="row in rows" :key="row.id" class="h-8 border-b border-mm-border">
          <td
            class="w-40 border-r border-mm-border bg-mm-fg/6 px-4 text-mm-muted-fg backdrop-blur-sm"
          >
            {{ labelOf(row) }}
          </td>
          <td class="px-4 break-all text-mm-fg">
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
          </td>
        </tr>
      </tbody>
    </table>

    <!--
      The raw file metadata (safetensors `__metadata__`) keeps its own table
      below the parsed information, exactly as the former "Metadata" tab
      rendered it - keys verbatim. It is skipped for download search results,
      whose `metadata` is the Civitai file metadata already surfaced (parsed)
      in the table above.
    -->
    <div v-if="rawRows.length" class="flex flex-col gap-2">
      <div class="text-sm font-medium text-mm-muted-fg">{{ $t('info.fileMetadata') }}</div>
      <table class="w-full border-collapse border border-mm-border">
        <tbody>
          <tr v-for="row in rawRows" :key="row.key" class="h-8 border-b border-mm-border">
            <td
              class="w-40 border-r border-mm-border bg-mm-fg/6 px-4 text-mm-muted-fg backdrop-blur-sm"
            >
              {{ row.key }}
            </td>
            <td class="px-4 break-all text-mm-fg">{{ row.value }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!rows.length && !rawRows.length" class="flex flex-col items-center gap-2 py-5">
      <!-- BUG FIX: `pi pi-info-circle` rendered empty (PrimeIcons removed). -->
      <Info class="size-5 text-mm-muted-fg" />
      <div class="text-sm text-mm-muted-fg">{{ $t('noMetadata') }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Info } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useModelDescription, useModelMetadata } from 'hooks/model'
import { type InformationRow, buildInformationRows } from 'utils/modelInformation'

const { t, te } = useI18n()

const { metadata, model } = useModelMetadata()
const { description } = useModelDescription()

const rows = computed<InformationRow[]>(() => buildInformationRows(description.value))

/** Localised labels win; verbatim keys render as-is. */
const labelOf = (row: InformationRow) => {
  if (row.labelKey && te(row.labelKey)) return t(row.labelKey)
  return row.labelRaw ?? row.labelKey ?? ''
}

const stringify = (value: unknown): string => {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

/**
 * Raw file metadata (safetensors `__metadata__`). Download search results
 * carry the Civitai *file* metadata here, which the parsed table above
 * already renders - showing it twice (including the `isRequired` / `size`
 * keys the table deliberately omits) would only be noise.
 */
const rawRows = computed(() => {
  const source = metadata.value
  if (!source || (model.value as any).downloadPlatform) return []
  const entries = Object.entries(source)
  if (!entries.length) return []
  return entries.map(([key, value]) => ({ key, value: stringify(value) }))
})
</script>
