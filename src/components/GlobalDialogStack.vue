<template>
  <template v-for="(item, index) in stack" :key="item.key">
    <Dialog
      v-if="states[item.key]"
      :open="item.visible ?? false"
      :modal="item.modal ?? false"
      @update:open="val => handleOpenChange(item, val)"
    >
      <DialogContent
        :show-close-button="false"
        :show-overlay="item.modal ?? false"
        :force-mount="item.keepAlive"
        :class="cn('flex max-h-full max-w-full flex-col p-0')"
        :style="{
          zIndex: 2400 + index,
          width: `${states[item.key].width}px`,
          height: `${states[item.key].height}px`,
          left: `${states[item.key].left}px`,
          top: `${states[item.key].top}px`,
          translate: '0 0',
        }"
        @escape-key-down="preventDismiss"
        @pointer-down-outside="preventDismiss"
        @focus-outside="preventDismiss"
        @interact-outside="preventDismiss"
        @mousedown="rise(item)"
      >
        <DialogHeader
          class="flex flex-row items-center justify-between space-y-0 border-b border-mm-border px-4 py-3 select-none"
          :class="allowResize && !states[item.key].isMaximized ? 'cursor-move' : 'cursor-default'"
          @mousedown.left="startDrag(item, $event)"
        >
          <DialogTitle class="text-base font-medium select-none">
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
            <Button v-if="allowResize" variant="ghost" size="icon-sm" @click="toggleMaximize(item)">
              <Maximize2 v-if="!states[item.key].isMaximized" class="size-4" />
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
        <div v-if="allowResize && !states[item.key].isMaximized" data-dialog-resizer>
          <div
            v-if="resizeAllowed(item).x"
            data-resize-pos="left"
            class="absolute top-0 -left-1 h-full w-2 cursor-ew-resize"
            @mousedown="startResize(item, $event)"
          ></div>
          <div
            v-if="resizeAllowed(item).x"
            data-resize-pos="right"
            class="absolute top-0 -right-1 h-full w-2 cursor-ew-resize"
            @mousedown="startResize(item, $event)"
          ></div>
          <div
            v-if="resizeAllowed(item).y"
            data-resize-pos="top"
            class="absolute -top-1 left-0 h-2 w-full cursor-ns-resize"
            @mousedown="startResize(item, $event)"
          ></div>
          <div
            v-if="resizeAllowed(item).y"
            data-resize-pos="bottom"
            class="absolute -bottom-1 left-0 h-2 w-full cursor-ns-resize"
            @mousedown="startResize(item, $event)"
          ></div>
          <div
            v-if="resizeAllowed(item).x && resizeAllowed(item).y"
            data-resize-pos="top-left"
            class="absolute -top-1 -left-1 size-2 cursor-se-resize"
            @mousedown="startResize(item, $event)"
          ></div>
          <div
            v-if="resizeAllowed(item).x && resizeAllowed(item).y"
            data-resize-pos="top-right"
            class="absolute -top-1 -right-1 size-2 cursor-sw-resize"
            @mousedown="startResize(item, $event)"
          ></div>
          <div
            v-if="resizeAllowed(item).x && resizeAllowed(item).y"
            data-resize-pos="bottom-left"
            class="absolute -bottom-1 -left-1 size-2 cursor-sw-resize"
            @mousedown="startResize(item, $event)"
          ></div>
          <div
            v-if="resizeAllowed(item).x && resizeAllowed(item).y"
            data-resize-pos="bottom-right"
            class="absolute -right-1 -bottom-1 size-2 cursor-se-resize"
            @mousedown="startResize(item, $event)"
          ></div>
        </div>
      </DialogContent>
    </Dialog>
  </template>
</template>

<script setup lang="ts">
import { Info, Maximize2, Minimize2, X } from '@lucide/vue'
import { clamp } from 'es-toolkit'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Button } from 'components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from 'components/ui/dialog'
import { useConfig } from 'hooks/config'
import { type DialogItem, useDialog } from 'hooks/dialog'
import { cn } from 'utils/cn'
import { resolveIcon } from 'utils/iconMap'

/**
 * Per-dialog window geometry.
 *
 * BUG FIX: this stack used to keep ONE shared size/position for every dialog
 * and ignored the per-dialog fields of `DialogItem` (`defaultSize`,
 * `defaultMobileSize`, `minWidth/maxWidth/minHeight/maxHeight`, `resizeAllow`,
 * `modal`). Those options are part of the dialog-store API and every caller
 * passes them (e.g. the 500×200 API-key dialog, the 680×490 scanning dialog,
 * the manager's minWidth derived from the card size). Each dialog now gets
 * its own state again — the behaviour the original PrimeVue-based
 * ResponseDialog had.
 */
interface DialogGeometry {
  width: number
  height: number
  left: number
  top: number
  isMaximized: boolean
  restore?: { width: number; height: number; left: number; top: number }
}

const { stack, rise, close } = useDialog()
const { isMobile } = useConfig()

const handleOpenChange = (item: DialogItem, val: boolean) => {
  if (!val) close(item)
}

/**
 * The original dialogs never closed on Escape or outside clicks
 * (`:close-on-escape="false"`, non-dismissable mask) — closing is explicit
 * via the X button / `dialog.close()`. Prevent reka-ui's default dismissal.
 */
const preventDismiss = (event: Event) => {
  event.preventDefault()
}

const allowResize = computed(() => !isMobile.value)

const constraintsFor = (item: Partial<DialogItem>) => ({
  minWidth: item.minWidth ?? 390,
  maxWidth: item.maxWidth ?? window.innerWidth,
  minHeight: item.minHeight ?? 390,
  maxHeight: item.maxHeight ?? window.innerHeight,
})

const resizeAllowed = (item: DialogItem) => ({ x: true, y: true, ...item.resizeAllow })

const createGeometry = (item: DialogItem): DialogGeometry => {
  if (isMobile.value) {
    return {
      width: item.defaultMobileSize?.width ?? window.innerWidth,
      height: item.defaultMobileSize?.height ?? window.innerHeight,
      left: 0,
      top: 0,
      isMaximized: false,
    }
  }

  const c = constraintsFor(item)
  const width = clamp(
    item.defaultSize?.width ?? window.innerWidth * 0.6,
    c.minWidth,
    Math.max(c.minWidth, c.maxWidth),
  )
  const height = clamp(
    item.defaultSize?.height ?? window.innerHeight * 0.8,
    c.minHeight,
    Math.max(c.minHeight, c.maxHeight),
  )

  return {
    width,
    height,
    left: (window.innerWidth - width) / 2,
    top: (window.innerHeight - height) / 2,
    isMaximized: false,
  }
}

/** Geometry per dialog key; kept while the dialog stays on the stack. */
const states = reactive<Record<string, DialogGeometry>>({})

watch(
  stack,
  items => {
    const alive = new Set(items.map(item => item.key))
    for (const key of Object.keys(states)) {
      if (!alive.has(key)) {
        delete states[key]
      }
    }
    for (const item of items) {
      if (!states[item.key]) {
        states[item.key] = createGeometry(item)
      }
    }
  },
  { deep: true, immediate: true },
)

// Switching between desktop and mobile layouts re-fits every open dialog.
watch(allowResize, resizable => {
  for (const item of stack.value) {
    const st = states[item.key]
    if (!st) continue
    if (resizable) {
      const c = constraintsFor(item)
      st.width = clamp(st.width, c.minWidth, Math.max(c.minWidth, window.innerWidth))
      st.height = clamp(st.height, c.minHeight, Math.max(c.minHeight, window.innerHeight))
      st.left = (window.innerWidth - st.width) / 2
      st.top = (window.innerHeight - st.height) / 2
    } else {
      st.width = window.innerWidth
      st.height = window.innerHeight
      st.left = 0
      st.top = 0
    }
    st.isMaximized = false
    st.restore = undefined
  }
})

const toggleMaximize = (item: DialogItem) => {
  const st = states[item.key]
  if (!st) return

  if (st.isMaximized) {
    const restore = st.restore
    st.isMaximized = false
    st.restore = undefined
    if (restore) {
      st.width = restore.width
      st.height = restore.height
      st.left = restore.left
      st.top = restore.top
    } else {
      const fresh = createGeometry(item)
      st.width = fresh.width
      st.height = fresh.height
      st.left = fresh.left
      st.top = fresh.top
    }
    return
  }

  st.restore = { width: st.width, height: st.height, left: st.left, top: st.top }
  st.width = window.innerWidth
  st.height = window.innerHeight
  st.left = 0
  st.top = 0
  st.isMaximized = true
}

/* ------------------------------------------------------------------ */
/* Resize                                                             */
/* ------------------------------------------------------------------ */
const resizeState = ref<{ key: string; directions: string[] } | null>(null)

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
  const rs = resizeState.value
  if (!rs) return
  const st = states[rs.key]
  if (!st) return

  const item = stack.value.find(candidate => candidate.key === rs.key)
  const c = constraintsFor(item ?? {})

  for (const direction of rs.directions) {
    if (direction === 'left') {
      if (event.clientX > 0) {
        st.width = clamp(st.left + st.width - event.clientX, c.minWidth, c.maxWidth)
      }
      if (st.width > c.minWidth && st.width < c.maxWidth) {
        st.left = clamp(event.clientX, 0, window.innerWidth - st.width)
      }
    }

    if (direction === 'right') {
      st.width = clamp(event.clientX - st.left, c.minWidth, c.maxWidth)
    }

    if (direction === 'top') {
      if (event.clientY > 0) {
        st.height = clamp(st.top + st.height - event.clientY, c.minHeight, c.maxHeight)
      }
      if (st.height > c.minHeight && st.height < c.maxHeight) {
        st.top = clamp(event.clientY, 0, window.innerHeight - st.height)
      }
    }

    if (direction === 'bottom') {
      st.height = clamp(event.clientY - st.top, c.minHeight, c.maxHeight)
    }
  }
}

const stopResize = () => {
  resizeState.value = null
  document.removeEventListener('mousemove', resize)
  document.removeEventListener('mouseup', stopResize)
  updateGlobalStyle()
}

const startResize = (item: DialogItem, event: MouseEvent) => {
  const direction = (event.target as HTMLElement).getAttribute('data-resize-pos') ?? ''
  resizeState.value = { key: item.key, directions: direction.split('-') }
  updateGlobalStyle(direction)
  document.addEventListener('mousemove', resize)
  document.addEventListener('mouseup', stopResize)
}

/* ------------------------------------------------------------------ */
/* Drag to move (parity with the draggable PrimeVue dialogs)          */
/* ------------------------------------------------------------------ */
const dragState = ref<{
  key: string
  startX: number
  startY: number
  originLeft: number
  originTop: number
} | null>(null)

const onDragMove = (event: MouseEvent) => {
  const d = dragState.value
  if (!d) return
  const st = states[d.key]
  if (!st) return

  st.left = clamp(
    d.originLeft + (event.clientX - d.startX),
    0,
    Math.max(0, window.innerWidth - st.width),
  )
  st.top = clamp(
    d.originTop + (event.clientY - d.startY),
    0,
    Math.max(0, window.innerHeight - st.height),
  )
}

const stopDrag = () => {
  dragState.value = null
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

const startDrag = (item: DialogItem, event: MouseEvent) => {
  if (!allowResize.value) return
  const st = states[item.key]
  if (!st || st.isMaximized) return
  // Never hijack clicks on the header buttons
  if ((event.target as HTMLElement).closest('button')) return

  dragState.value = {
    key: item.key,
    startX: event.clientX,
    startY: event.clientY,
    originLeft: st.left,
    originTop: st.top,
  }
  document.body.style.cursor = 'move'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', stopDrag)
}

onBeforeUnmount(() => {
  stopResize()
  stopDrag()
})
</script>
