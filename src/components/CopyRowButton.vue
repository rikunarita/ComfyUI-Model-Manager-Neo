<script setup lang="ts">
/**
 * Hover-revealed copy button pinned to the LEFT edge of the visible table
 * panel (the parent wrapper carries `group relative` and the horizontal
 * scroll port). Pinning it to the wrapper - instead of to a table cell -
 * keeps it inside the visible range while wide rows scroll sideways; it
 * copies whatever row the pointer rests on (`text`).
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
    class="absolute top-1/2 left-1 z-10 -translate-y-1/2 bg-mm-bg/85 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
    :title="t('copyRow')"
    :aria-label="t('copyRow')"
    @click.stop="copyText(text)"
  >
    <Copy class="size-3.5" />
  </Button>
</template>
