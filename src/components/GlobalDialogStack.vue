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
        width: `${containerSize.width}px`,
        height: `${containerSize.height}px`,
        left: `${containerPosition.left}px`,
        top: `${containerPosition.top}px`,
        translate: '0 0',
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
            <component
              :is="resolveIcon(action.icon) || Info"
              class="size-4"
              :class="{ 'animate-spin': action.icon === 'pi pi-spinner pi-spin' }"
            />
          </Button>
          <Button
            v-if="allowResize"
            variant="ghost"
            size="icon-sm"
            @click="toggleMaximize"
          >
            <Maximize2 v-if="!isMaximized" class="size-4" />
            <Minimize2 v-else class="size-4" />
          </Button>
          <Button variant="ghost" size="icon-sm" @click="close(item)">
            <X class="size-4" />
          </Button>
        </div>
      </DialogHeader>
      <div class="min-h-0 flex-1 overflow-auto">
        <component :is="item.content" v-bind="item.contentProps" />
      </div>

      <!-- Resize handles -->
      <div v-if="allowResize && !isMaximized" data-dialog-resizer>
        <div
          v-if="resizeAllow?.x"
          data-resize-pos="left"
          class="absolute -left-1 top-0 h-full w-2 cursor-ew-resize"
          @mousedown="startResize"
        ></div>
        <div
          v-if="resizeAllow?.x"
          data-resize-pos="right"
          class="absolute -right-1 top-0 h-full w-2 cursor-ew-resize"
          @mousedown="startResize"
        ></div>
        <div
          v-if="resizeAllow?.y"
          data-resize-pos="top"
          class="absolute -top-1 left-0 h-2 w-full cursor-ns-resize"
          @mousedown="startResize"
        ></div>
        <div
          v-if="resizeAllow?.y"
          data-resize-pos="bottom"
          class="absolute -bottom-1 left-0 h-2 w-full cursor-ns-resize"
          @mousedown="startResize"
        ></div>
        <div
          v-if="resizeAllow?.x && resizeAllow?.y"
          data-resize-pos="top-left"
          class="absolute -left-1 -top-1 h-2 w-2 cursor-se-resize"
          @mousedown="startResize"
        ></div>
        <div
          v-if="resizeAllow?.x && resizeAllow?.y"
          data-resize-pos="top-right"
          class="absolute -right-1 -top-1 h-2 w-2 cursor-sw-resize"
          @mousedown="startResize"
        ></div>
        <div
          v-if="resizeAllow?.x && resizeAllow?.y"
          data-resize-pos="bottom-left"
          class="absolute -bottom-1 -left-1 h-2 w-2 cursor-sw-resize"
          @mousedown="startResize"
        ></div>
        <div
          v-if="resizeAllow?.x && resizeAllow?.y"
          data-resize-pos="bottom-right"
          class="absolute -bottom-1 -right-1 h-2 w-2 cursor-se-resize"
          @mousedown="startResize"
        ></div>
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { Maximize2, Minimize2, X } from '@lucide/vue'
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const { stack, rise, close } = useDialog()
const { isMobile } = useConfig()

const handleOpenChange = (item: DialogItem, val: boolean) => {
  if (!val) close(item)
}

const allowResize = computed(() => !isMobile.value)
const resizeAllow = computed(() => ({ x: true, y: true }))

const isMaximized = ref(false)
const isResizing = ref(false)
const resizeDirection = ref<string[]>([])

const defaultWidth = window.innerWidth * 0.6
const defaultHeight = window.innerHeight * 0.8

// 修正1: 初期サイズ
const containerSize = ref({
  width: defaultWidth,
  height: defaultHeight,
})

// 修正2: 初期位置を画面中央に（left/top=0 ＋ translate残存による偏移を根絶）
const centerPosition = (size: { width: number; height: number }) => ({
  left: (window.innerWidth - size.width) / 2,
  top: (window.innerHeight - size.height) / 2,
})

const containerPosition = ref(centerPosition(containerSize.value))

const minWidth = computed(() => 390)
const maxWidth = computed(() => window.innerWidth)
const minHeight = computed(() => 390)
const maxHeight = computed(() => window.innerHeight)

const updateContainerSize = (size: { width: number; height: number }) => {
  containerSize.value = size
}

const updateContainerPosition = (position: { left: number; top: number }) => {
  containerPosition.value = position
}

const updateGlobalStyle = (direction?: string) => {
  let cursor = ''
  let select = ''
  switch (direction) {
    case 'left':
    case 'right':
      cursor = 'ew-resize'
      select = 'none'
      break
    case 'top':
    case 'bottom':
      cursor = 'ns-resize'
      select = 'none'
      break
    case 'top-left':
    case 'bottom-right':
      cursor = 'se-resize'
      select = 'none'
      break
    case 'top-right':
    case 'bottom-left':
      cursor = 'sw-resize'
      select = 'none'
      break
    default:
      break
  }
  document.body.style.cursor = cursor
  document.body.style.userSelect = select
}

const resize = (event: MouseEvent) => {
  if (isResizing.value) {
    for (const direction of resizeDirection.value) {
      if (direction === 'left') {
        if (event.clientX > 0) {
          containerSize.value.width = clamp(
            containerPosition.value.left + containerSize.value.width - event.clientX,
            minWidth.value,
            maxWidth.value,
          )
        }
        if (
          containerSize.value.width > minWidth.value &&
          containerSize.value.width < maxWidth.value
        ) {
          containerPosition.value.left = clamp(
            event.clientX,
            0,
            window.innerWidth - containerSize.value.width,
          )
        }
      }

      if (direction === 'right') {
        containerSize.value.width = clamp(
          event.clientX - containerPosition.value.left,
          minWidth.value,
          maxWidth.value,
        )
      }

      if (direction === 'top') {
        if (event.clientY > 0) {
          containerSize.value.height = clamp(
            containerPosition.value.top + containerSize.value.height - event.clientY,
            minHeight.value,
            maxHeight.value,
          )
        }
        if (
          containerSize.value.height > minHeight.value &&
          containerSize.value.height < maxHeight.value
        ) {
          containerPosition.value.top = clamp(
            event.clientY,
            0,
            window.innerHeight - containerSize.value.height,
          )
        }
      }

      if (direction === 'bottom') {
        containerSize.value.height = clamp(
          event.clientY - containerPosition.value.top,
          minHeight.value,
          maxHeight.value,
        )
      }
    }
    updateContainerSize(containerSize.value)
    updateContainerPosition(containerPosition.value)
  }
}

const stopResize = () => {
  isResizing.value = false
  resizeDirection.value = []
  document.removeEventListener('mousemove', resize)
  document.removeEventListener('mouseup', stopResize)
  updateGlobalStyle()
}

const startResize = (event: MouseEvent) => {
  isResizing.value = true
  const direction =
    (event.target as HTMLElement).getAttribute('data-resize-pos') ?? ''
  resizeDirection.value = direction.split('-')
  updateGlobalStyle(direction)
  document.addEventListener('mousemove', resize)
  document.addEventListener('mouseup', stopResize)
}

// 修正3: 最大化復元時も中央へ戻す
const toggleMaximize = () => {
  if (isMaximized.value) {
    updateContainerSize({ width: defaultWidth, height: defaultHeight })
    updateContainerPosition(centerPosition({ width: defaultWidth, height: defaultHeight }))
    isMaximized.value = false
  } else {
    updateContainerSize({ width: window.innerWidth, height: window.innerHeight })
    updateContainerPosition({ left: 0, top: 0 })
    isMaximized.value = true
  }
}

onMounted(() => {
  nextTick(() => {
    if (allowResize.value) {
      updateContainerSize(containerSize.value)
      updateContainerPosition(centerPosition(containerSize.value))
    } else {
      updateContainerSize({
        width: window.innerWidth,
        height: window.innerHeight,
      })
      updateContainerPosition({ left: 0, top: 0 })
    }
  })
})

onBeforeUnmount(() => {
  stopResize()
})

watch(allowResize, (allowResize) => {
  if (allowResize) {
    updateContainerSize(containerSize.value)
    updateContainerPosition(centerPosition(containerSize.value))
  } else {
    updateContainerSize({
      width: window.innerWidth,
      height: window.innerHeight,
    })
    updateContainerPosition({ left: 0, top: 0 })
  }
})
</script>
