<template>
  <Dialog
    v-for="(item, index) in stack"
    :key="item.key"
    :open="item.visible ?? false"
    @update:open="(val) => handleOpenChange(item, val)"
  >
    <DialogContent
      :show-close-button="false"
      :force-mount="item.keepAlive"
      :class="cn('flex max-h-full max-w-full flex-col p-0')"
      :style="{
        zIndex: 2400 + index,
        width: `${sizeOf(item).width}px`,
        height: `${sizeOf(item).height}px`,
      }"
      @mousedown="rise(item)"
    >
      <DialogHeader
        class="flex flex-row items-center justify-between space-y-0 border-b border-mm-border px-4 py-3"
      >
        <DialogTitle class="select-none text-base font-medium">
          {{ item.title }}
        </DialogTitle>
        <div class="flex items-center gap-1">
          <Button
            v-for="action in item.headerButtons"
            :key="action.key"
            variant="ghost"
            size="icon-sm"
            :title="action.tooltip"
            @click.stop="action.command"
          >
            <i :class="action.icon" />
          </Button>
          <Button variant="ghost" size="icon-sm" @click="close(item)">
            <X class="size-4" />
          </Button>
        </div>
      </DialogHeader>
      <div class="min-h-0 flex-1 overflow-auto">
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
  DialogContent,
  DialogHeader,
  DialogTitle,
} from 'components/ui/dialog'
import { useConfig } from 'hooks/config'
import type { DialogItem } from 'hooks/dialog'
import { useDialog } from 'hooks/dialog'
import { clamp } from 'es-toolkit'
import { cn } from 'utils/cn'

const { stack, rise, close } = useDialog()
const { isMobile } = useConfig()

const handleOpenChange = (item: DialogItem, val: boolean) => {
  if (!val) close(item)
}

// 旧 ResponseDialog のサイズ機構を復元
const sizeOf = (item: DialogItem) => {
  if (isMobile.value) {
    return {
      width: item.defaultMobileSize?.width ?? window.innerWidth,
      height: item.defaultMobileSize?.height ?? window.innerHeight,
    }
  }
  const defW = window.innerWidth * 0.6
  const defH = window.innerHeight * 0.8
  return {
    width: clamp(
      item.defaultSize?.width ?? defW,
      item.minWidth ?? 390,
      item.maxWidth ?? window.innerWidth,
    ),
    height: clamp(
      item.defaultSize?.height ?? defH,
      item.minHeight ?? 390,
      item.maxHeight ?? window.innerHeight,
    ),
  }
}
</script>
