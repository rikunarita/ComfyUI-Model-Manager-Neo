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
        :overlay-style="{ zIndex: dialogZ(index) }"
        :force-mount="item.keepAlive"
        :class="cn('flex max-h-full max-w-full flex-col p-0')"
        :style="{
          zIndex: dialogZ(index),
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
        <DialogHeaderBar
          :item="item"
          :maximized="states[item.key].isMaximized"
          :resizable="allowResize"
          :movable="allowResize && !states[item.key].isMaximized"
          @drag="startDrag(item, $event)"
          @maximize="toggleMaximize(item)"
          @close="close(item)"
        />
        <div class="min-h-0 flex-1 overflow-auto">
          <component :is="item.content" v-bind="item.contentProps" />
        </div>

        <!--
          Loading is panel-scoped: only the topmost window gets the scrim, so
          the rest of ComfyUI (canvas, top bar, other panels) stays visible and
          usable while this extension works. See components/PanelLoading.vue.
        -->
        <PanelLoading v-if="loading && index === topmostVisibleIndex" />

        <DialogResizeHandles
          v-if="allowResize && !states[item.key].isMaximized"
          :allow-x="resizeAllowed(item).x"
          :allow-y="resizeAllowed(item).y"
          @resize="startResize(item, $event)"
        />
      </DialogContent>
    </Dialog>
  </template>
</template>

<script setup lang="ts">
import { clamp } from 'es-toolkit'
import { computed, onBeforeUnmount, onErrorCaptured, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import DialogHeaderBar from 'components/DialogHeaderBar.vue'
import DialogResizeHandles from 'components/DialogResizeHandles.vue'
import PanelLoading from 'components/PanelLoading.vue'
import { Dialog, DialogContent } from 'components/ui/dialog'
import { useConfig } from 'hooks/config'
import { type DialogItem, useDialog } from 'hooks/dialog'
import { useGlobalLoading } from 'hooks/loading'
import { useToast } from 'hooks/toast'
import { cn } from 'utils/cn'

/**
 * Per-dialog window geometry.
 *
 * BUG FIX: this stack used to keep ONE shared size/position for every dialog
 * and ignored the per-dialog fields of `DialogItem` (`defaultSize`,
 * `defaultMobileSize`, `minWidth/maxWidth/minHeight/maxHeight`, `resizeAllow`,
 * `modal`). Those options are part of the dialog-store API and every caller
 * passes them (e.g. the 500×200 API-key dialog, the 500×390 card-size dialog,
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
const { loading } = useGlobalLoading()
const { toast } = useToast()
const { t } = useI18n()

/**
 * SAFETY NET: when a window's content throws while mounting, Vue keeps the
 * already-inserted partial subtree and the window silently shows half a UI
 * (exactly how the "completely broken" download dialog read - no message,
 * no clue). Surface any render error of any window as a toast + console
 * report instead, so a regression can never hide behind an empty panel again.
 */
onErrorCaptured((err, _instance, info) => {
  console.error('[Model Manager Neo] window render error:', err, info)
  toast.add({
    severity: 'error',
    summary: t('error'),
    detail: `${err instanceof Error ? err.message : String(err)} (${info})`,
    life: 15000,
  })
  // handled: one toast per error, never tear down the whole app
  return false
})

/**
 * Index of the window that is on top AND actually shown. `keepAlive` dialogs
 * stay on the stack with `visible: false`, so the last array entry is not
 * necessarily the one the user is looking at.
 */
const topmostVisibleIndex = computed(() => {
  for (let i = stack.value.length - 1; i >= 0; i--) {
    if (stack.value[i].visible !== false) return i
  }
  return -1
})

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

/**
 * Stacking position of window `index` in the dialog stack.
 *
 * Expressed against the `--mm-z-dialog` token (see src/style.css) rather than
 * as a bare literal so the whole scale lives in one place: anchored popups
 * (select / dropdown / tooltip), nested dialogs, the global confirm and the
 * toasts are all positioned relative to the same base, and `rise()` moving a
 * window to the end of the stack still puts it on top.
 */
const dialogZ = (index: number) => `calc(var(--mm-z-dialog) + ${index})`

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
        continue
      }
      // Re-showing a keepAlive window: never let it come back half off-screen
      // (e.g. it was parked near an edge and the viewport shrank since).
      if (item.visible !== false) {
        const st = states[item.key]
        st.left = clamp(st.left, 0, Math.max(0, window.innerWidth - st.width))
        st.top = clamp(st.top, 0, Math.max(0, window.innerHeight - st.height))
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
      userPositioned.delete(item.key)
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

/**
 * Viewport changes (window resize, fullscreen or zoom changes) re-centre
 * every dialog the user never positioned by hand and clamp the rest into
 * view, so no panel can end up sitting off-centre or half off-screen without
 * an explicit gesture - the "the panel drifted on its own" defect.
 */
const repositionAll = () => {
  for (const item of stack.value) {
    const st = states[item.key]
    if (!st) continue
    if (st.isMaximized) {
      st.width = window.innerWidth
      st.height = window.innerHeight
      st.left = 0
      st.top = 0
      continue
    }
    if (!userPositioned.has(item.key)) {
      const fresh = createGeometry(item)
      st.width = fresh.width
      st.height = fresh.height
      st.left = fresh.left
      st.top = fresh.top
      continue
    }
    const c = constraintsFor(item)
    st.width = clamp(st.width, c.minWidth, Math.max(c.minWidth, window.innerWidth))
    st.height = clamp(st.height, c.minHeight, Math.max(c.minHeight, window.innerHeight))
    st.left = clamp(st.left, 0, Math.max(0, window.innerWidth - st.width))
    st.top = clamp(st.top, 0, Math.max(0, window.innerHeight - st.height))
  }
}

window.addEventListener('resize', repositionAll)

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
/**
 * Keys whose geometry the user positioned by hand (drag / resize past the
 * gesture threshold). Everything else re-centres when the viewport changes,
 * so a window resize / fullscreen toggle / zoom change can never leave a
 * panel sitting off-centre ("the panel drifted without me moving it").
 */
const userPositioned = new Set<string>()

/** Pixels a press must travel before it counts as a move gesture. */
const GESTURE_THRESHOLD = 3

const resizeState = ref<{
  key: string
  directions: string[]
  startX: number
  startY: number
  applied: boolean
} | null>(null)

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

type Geometry = DialogGeometry
type Limits = { minWidth: number; maxWidth: number; minHeight: number; maxHeight: number }

/**
 * One handler per resize direction, clamped to the window limits. A lookup
 * table keeps the dispatch branch-free.
 */
const RESIZE_HANDLERS: Record<string, (event: MouseEvent, st: Geometry, c: Limits) => void> = {
  left: (event, st, c) => {
    if (event.clientX > 0) {
      st.width = clamp(st.left + st.width - event.clientX, c.minWidth, c.maxWidth)
    }
    if (st.width > c.minWidth && st.width < c.maxWidth) {
      st.left = clamp(event.clientX, 0, window.innerWidth - st.width)
    }
  },
  right: (event, st, c) => {
    st.width = clamp(event.clientX - st.left, c.minWidth, c.maxWidth)
  },
  top: (event, st, c) => {
    if (event.clientY > 0) {
      st.height = clamp(st.top + st.height - event.clientY, c.minHeight, c.maxHeight)
    }
    if (st.height > c.minHeight && st.height < c.maxHeight) {
      st.top = clamp(event.clientY, 0, window.innerHeight - st.height)
    }
  },
  bottom: (event, st, c) => {
    st.height = clamp(event.clientY - st.top, c.minHeight, c.maxHeight)
  },
}

const resize = (event: MouseEvent) => {
  const rs = resizeState.value
  if (!rs) return
  const st = states[rs.key]
  if (!st) return

  if (!rs.applied) {
    if (Math.hypot(event.clientX - rs.startX, event.clientY - rs.startY) < GESTURE_THRESHOLD) return
    rs.applied = true
    userPositioned.add(rs.key)
  }

  const item = stack.value.find(candidate => candidate.key === rs.key)
  const c = constraintsFor(item ?? {})

  for (const direction of rs.directions) {
    RESIZE_HANDLERS[direction]?.(event, st, c)
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
  resizeState.value = {
    key: item.key,
    directions: direction.split('-'),
    startX: event.clientX,
    startY: event.clientY,
    applied: false,
  }
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
  moved: boolean
} | null>(null)

const onDragMove = (event: MouseEvent) => {
  const d = dragState.value
  if (!d) return
  const st = states[d.key]
  if (!st) return

  const dx = event.clientX - d.startX
  const dy = event.clientY - d.startY
  if (!d.moved) {
    if (Math.hypot(dx, dy) < GESTURE_THRESHOLD) return
    d.moved = true
    userPositioned.add(d.key)
  }

  st.left = clamp(d.originLeft + dx, 0, Math.max(0, window.innerWidth - st.width))
  st.top = clamp(d.originTop + dy, 0, Math.max(0, window.innerHeight - st.height))
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
    moved: false,
  }
  document.body.style.cursor = 'move'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', stopDrag)
}

onBeforeUnmount(() => {
  stopResize()
  stopDrag()
  window.removeEventListener('resize', repositionAll)
})
</script>
