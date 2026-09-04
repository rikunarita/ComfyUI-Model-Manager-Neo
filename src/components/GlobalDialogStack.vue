<template>
  <Dialog
    v-for="(item, index) in stack"
    :key="item.key"
    :open="item.visible ?? false"
    @update:open="(val) => handleOpenChange(item, val)"
  >
    <DialogContent
      :class="cn(
        'mm-glass max-h-[90vh] max-w-[90vw] p-0',
        item.modal === false && 'pointer-events-auto',
      )"
      :style="{
        zIndex: 2400 + index,
        width: item.defaultSize?.width ? `${item.defaultSize.width}px` : undefined,
        height: item.defaultSize?.height ? `${item.defaultSize.height}px` : undefined,
        minWidth: item.minWidth ? `${item.minWidth}px` : undefined,
        maxWidth: item.maxWidth ? `${item.maxWidth}px` : undefined,
        minHeight: item.minHeight ? `${item.minHeight}px` : undefined,
        maxHeight: item.maxHeight ? `${item.maxHeight}px` : undefined,
      }"
      @mousedown="rise(item)"
    >
      <DialogHeader class="flex flex-row items-center justify-between space-y-0 border-b border-mm-border p-4">
        <DialogTitle class="select-none text-base font-medium">
          {{ item.title }}
        </DialogTitle>
        <div class="flex items-center gap-1">
          <Button
            v-for="action in item.headerButtons"
            :key="action.key"
            variant="ghost"
            size="icon-xs"
            :title="action.tooltip"
            @click.stop="action.command"
          >
            <component :is="getIcon(action.icon)" class="size-4" />
          </Button>
          <DialogClose as-child>
            <Button variant="ghost" size="icon-xs" @click="close(item)">
              <X class="size-4" />
            </Button>
          </DialogClose>
        </div>
      </DialogHeader>
      <div class="flex-1 overflow-auto p-4">
        <component :is="item.content" v-bind="item.contentProps" />
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { X } from '@lucide/vue'
import { Button } from 'components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from 'components/ui/dialog'
import type { DialogItem } from 'hooks/dialog'
import { useDialog } from 'hooks/dialog'
import { cn } from 'utils/cn'
import { computed, h } from 'vue'

const { stack, rise, close } = useDialog()

const handleOpenChange = (item: DialogItem & { visible?: boolean }, val: boolean) => {
  if (!val) {
    close(item)
  }
}

// Icon mapping: PrimeIcons/MaterialDesign → Lucide
const getIcon = (icon: string) => {
  // Simple mapping for common icons
  const map: Record<string, any> = {
    'pi pi-refresh': 'RefreshCw',
    'pi pi-download': 'Download',
    'pi pi-upload': 'Upload',
    'pi pi-folder-search-out': 'FolderSearch',
    'md md-folder-search-out': 'FolderSearch',
  }
  // For now, return a simple span with the icon class (PrimeIcons still loaded)
  // In 3+5-7, replace with actual Lucide components
  return {
    render: () => h('i', { class: icon }),
  }
}
</script>
