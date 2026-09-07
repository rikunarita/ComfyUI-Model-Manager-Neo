<template>
  <!-- Drop mode: DropdownMenu (self-managed open state) -->
  <slot v-if="type === 'drop'" name="target" v-bind="{ prefixIcon, currentLabel, current }">
    <DropdownMenu>
      <DropdownMenuTrigger as-child :class="$attrs.class">
        <Button variant="secondary" class="-my-1 w-full py-1 whitespace-nowrap">
          <slot name="prefix">
            <!-- 修正: クラス文字列は <i> の class として描画（元実装の方式） -->
            <i v-if="prefixIcon" :class="prefixIcon" class="text-base opacity-60"></i>
          </slot>
          <span class="flex-1 scrollbar-none overflow-scroll text-right">
            <slot name="label">{{ currentLabel }}</slot>
          </span>
          <slot name="suffix">
            <ChevronDown class="size-4 opacity-60" />
          </slot>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="max-h-75 min-w-32 overflow-y-auto">
        <DropdownMenuItem
          v-for="item in items"
          :key="item.value"
          class="justify-between"
          @select="item.command?.()"
        >
          <slot name="item" :item="item">
            <span>{{ item.label }}</span>
          </slot>
          <Check v-if="current === item.value" class="size-4 text-mm-accent" />
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </slot>

  <!-- Button mode: segmented buttons with horizontal scroll -->
  <div v-else class="relative flex-1 overflow-hidden">
    <div ref="scrollArea" class="size-full scrollbar-none overflow-auto">
      <div ref="contentArea" class="table max-w-full">
        <div
          v-show="showControlButton && scrollPosition !== 'left'"
          :class="[
            'pointer-events-none absolute z-10 flex h-full items-center',
            'top-1/2 transform-[translateY(-50%)]',
            'left-0 pr-4',
            'bg-[linear-gradient(to_right,var(--mm-bg),transparent)]',
          ]"
        >
          <Button
            variant="ghost"
            size="icon-xs"
            class="pointer-events-auto border-none bg-transparent"
            @click="scrollTo('prev')"
          >
            <ChevronLeft class="size-4" />
          </Button>
        </div>
        <div class="flex h-10 items-center gap-2">
          <Button
            v-for="item in items"
            :key="item.value"
            :data-active="current === item.value"
            class="whitespace-nowrap data-[active=true]:bg-mm-surface-selected data-[active=true]:text-mm-accent"
            variant="secondary"
            :size="mappedSize"
            @click="item.command?.()"
          >
            <span>{{ item.label }}</span>
          </Button>
        </div>
        <div
          v-show="showControlButton && scrollPosition !== 'right'"
          :class="[
            'pointer-events-none absolute z-10 flex h-full items-center',
            'top-1/2 transform-[translateY(-50%)]',
            'right-0 pl-4',
            'bg-[linear-gradient(to_left,var(--mm-bg),transparent)]',
          ]"
        >
          <Button
            variant="ghost"
            size="icon-xs"
            class="pointer-events-auto border-none bg-transparent"
            @click="scrollTo('next')"
          >
            <ChevronRight class="size-4" />
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Check, ChevronDown, ChevronLeft, ChevronRight } from '@lucide/vue'
import { useElementSize, useScroll } from '@vueuse/core'
import { computed, ref } from 'vue'
import { Button } from 'components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from 'components/ui/dropdown-menu'
import { type SelectOptions } from 'types/typings'

interface Props {
  items?: SelectOptions[]
  rounded?: boolean
  text?: boolean
  severity?: 'secondary' | 'info' | 'success' | 'warning' | 'danger' | 'help'
  size?: 'small' | 'large'
  type?: 'button' | 'drop'
}

const props = withDefaults(defineProps<Props>(), {
  severity: 'secondary',
  type: 'drop',
})

defineOptions({ inheritAttrs: false })

const current = defineModel<any>()

// size mapping: 'small' → 'sm', 'large' → 'lg'
const mappedSize = computed(() => {
  if (props.size === 'small') return 'sm' as const
  if (props.size === 'large') return 'lg' as const
  return 'default' as const
})

const prefixIcon = computed(() => {
  return props.items?.find(item => item.value === current.value)?.icon
})

const currentLabel = computed(() => {
  return props.items?.find(item => item.value === current.value)?.label
})

// Button mode: horizontal scroll controls
const scrollArea = ref<HTMLElement | null>(null)
const contentArea = ref<HTMLElement | null>(null)

// Three states: at the left edge, somewhere in the middle, at the right edge.
// The middle state must show *both* arrows; collapsing it into 'left' (as
// before) hid the "previous" arrow while there was still content to the left.
type ScrollPosition = 'left' | 'middle' | 'right'

// Reactive size tracking for BOTH the viewport and its content, so the
// controls update on scroll *and* on container resize (the previous
// implementation read `scrollWidth`/`clientWidth` imperatively inside a
// computed, which is not reactive and never refreshed after mount).
const { width: viewportWidth } = useElementSize(scrollArea)
const { width: contentWidth } = useElementSize(contentArea)
const { x: scrollX } = useScroll(scrollArea)

const showControlButton = computed(() => {
  return contentWidth.value > viewportWidth.value + 1
})

const scrollPosition = computed<ScrollPosition>(() => {
  const maxScroll = contentWidth.value - viewportWidth.value
  if (maxScroll <= 1 || scrollX.value <= 0) {
    return 'left'
  }
  if (Math.ceil(scrollX.value) >= Math.floor(maxScroll)) {
    return 'right'
  }
  return 'middle'
})

const scrollTo = (direction: 'prev' | 'next') => {
  if (!scrollArea.value) return
  const step = (scrollArea.value.clientWidth / 3) * 2
  scrollArea.value.scrollBy({
    left: direction === 'prev' ? -step : step,
    behavior: 'smooth',
  })
}
</script>
