<script setup lang="ts">
/**
 * Per-row copy button of the detail tables (base info + information).
 *
 * The button lives in a `position: sticky; right: 0` cell at the end of each
 * row: when a row is wider than the panel and the table scrolls sideways,
 * the cell stays pinned to the RIGHT edge of the visible scroll port, so the
 * button is always inside the visible range; on narrow rows it simply sits
 * at the row's end. Revealed by hovering (or focusing) its own row - the row
 * carries the `group` class.
 */
import { Copy } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { Button } from 'components/ui/button'
import { useCopyText } from 'hooks/clipboard'

defineProps<{ text: string }>()

const { t } = useI18n()
const { copyText } = useCopyText()
</script>

<template>
  <Button
    variant="ghost"
    size="icon-xs"
    class="bg-mm-bg/85 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
    :title="t('copyRow')"
    :aria-label="t('copyRow')"
    @click.stop="copyText(text)"
  >
    <Copy class="size-3.5" />
  </Button>
</template>
