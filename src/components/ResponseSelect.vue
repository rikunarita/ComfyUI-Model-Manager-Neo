<template>
  <!-- Drop mode: DropdownMenu (self-managed open state) -->
  <slot
    v-if="type === 'drop'"
    name="target"
    v-bind="{ prefixIcon, currentLabel, current }"
  >
    <DropdownMenu>
      <DropdownMenuTrigger as-child :class="$attrs.class">
        <Button variant="secondary" class="-my-1 w-full whitespace-nowrap py-1">
          <slot name="prefix">
            <!-- 修正: クラス文字列は <i> の class として描画（元実装の方式） -->
            <i v-if="prefixIcon" :class="prefixIcon" class="text-base opacity-60"></i>
          </slot>
          <span class="flex-1 overflow-scroll text-right scrollbar-none">
            <slot name="label">{{ currentLabel }}</slot>
          </span>
          <slot name="suffix">
            <ChevronDown class="size-4 opacity-60" />
          </slot>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        class="max-h-[300px] min-w-[8rem] overflow-y-auto"
      >
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
    <div ref="scrollArea" class="h-full w-full overflow-auto scrollbar-none">
      <div ref="contentArea" class="table max-w-full">
        <div
          v-show="showControlButton && scrollPosition !== 'left'"
          :class="[
            'pointer-events-none absolute z-10 flex h-full items-center',
            'top-1/2 [transform:translateY(-50%)]',
            'left-0 pr-4',
            '[background-image:linear-gradient(to_right,var(--mm-bg),transparent)]',
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
            'top-1/2 [transform:translateY(-50%)]',
            'right-0 pl-4',
            '[background-image:linear-gradient(to_left,var(--mm-bg),transparent)]',
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
import { Button } from 'components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from 'components/ui/dropdown-menu'
import type { SelectOptions } from 'types/typings'
import { computed, ref, watch } from 'vue'

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

const current = defineModel()

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

type ScrollPosition = 'left' | 'right'

const { width, height } = useElementSize(scrollArea)
const { x: scrollX } = useScroll(scrollArea)

const showControlButton = computed(() => {
  if (!contentArea.value || !scrollArea.value) return false
  return contentArea.value.scrollWidth > scrollArea.value.clientWidth
})

const scrollPosition = computed<ScrollPosition>(() => {
  if (!scrollArea.value) return 'left'
  const maxScroll = scrollArea.value.scrollWidth - scrollArea.value.clientWidth
  if (scrollX.value <= 0) return 'left'
  if (scrollX.value >= maxScroll) return 'right'
  return 'left'
})

const scrollTo = (direction: 'prev' | 'next') => {
  if (!scrollArea.value) return
  const step = (scrollArea.value.clientWidth / 3) * 2
  scrollArea.value.scrollBy({
    left: direction === 'prev' ? -step : step,
    behavior: 'smooth',
  })
}

watch([width, height], () => {
  // re-evaluation handled by computeds
})
</script>
