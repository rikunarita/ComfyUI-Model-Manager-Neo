<script setup lang="ts">
import { Info, Maximize2, Minimize2, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { Button } from 'components/ui/button'
import { DialogHeader, DialogTitle } from 'components/ui/dialog'
import { type DialogItem } from 'hooks/dialog'
import { resolveIcon } from 'utils/iconMap'

interface Props {
  item: DialogItem
  maximized: boolean
  resizable: boolean
  movable: boolean
}
defineProps<Props>()

const emits = defineEmits<{
  drag: [event: MouseEvent]
  maximize: []
  close: []
}>()

const { t } = useI18n()
</script>

<template>
  <!--
    Title bar of every manager window: action buttons, maximize/restore and
    close, plus the drag-to-move grip. Extracted from GlobalDialogStack to
    keep that template below the complexity hot-spot band.
  -->
  <DialogHeader
    class="flex flex-row items-center justify-between space-y-0 border-b border-mm-border px-4 py-3 select-none"
    :class="movable ? 'cursor-move' : 'cursor-default'"
    @mousedown.left="emits('drag', $event)"
  >
    <DialogTitle class="text-base font-medium select-none">
      {{ item.title }}
    </DialogTitle>
    <div class="flex items-center gap-1">
      <Button
        v-for="action in item.headerButtons"
        :key="action.key"
        variant="ghost"
        size="icon-header"
        :title="action.tooltip"
        :aria-label="action.tooltip"
        @click.stop="action.command"
      >
        <component
          :is="resolveIcon(action.icon) || Info"
          class="size-4"
          :class="{ 'animate-spin': action.icon === 'pi pi-spinner pi-spin' }"
        />
      </Button>
      <Button
        v-if="resizable"
        variant="ghost"
        size="icon-header"
        :title="maximized ? t('restore') : t('maximize')"
        :aria-label="maximized ? t('restore') : t('maximize')"
        @click="emits('maximize')"
      >
        <Maximize2 v-if="!maximized" class="size-4" />
        <Minimize2 v-else class="size-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon-header"
        :title="t('close')"
        :aria-label="t('close')"
        @click="emits('close')"
      >
        <X class="size-4" />
      </Button>
    </div>
  </DialogHeader>
</template>
