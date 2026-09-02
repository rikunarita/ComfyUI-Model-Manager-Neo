<script setup lang="ts">
import { Check, ChevronDown, ChevronLeft, ChevronRight } from '@lucide/vue'
import { Button } from 'components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from 'components/ui/dropdown-menu'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from 'components/ui/sheet'
import { useConfig } from 'hooks/config'
import type { SelectOptions } from 'types/typings'
import { useElementSize, useScroll } from '@vueuse/core'
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
  type: 'button',
})

const current = defineModel()

const suffixIcon = ref('pi pi-angle-down')
const prefixIcon = computed(() => {
  return props.items?.find((item) => item.value === current.value)?.icon
})

const currentLabel = computed(() => {
  return props.items?.find((item) => item.value === current.value)?.label
})

const menu = ref()
const visible = ref(false)

const { isMobile } = useConfig()

const toggle = (event: MouseEvent) => {
  if (isMobile.value) {
    visible.value = !visible.value
  }
}

const overlayVisible = computed(() => {
  return isMobile.value ? visible.value : false
})

// size マッピング: 'small' → 'sm', 'large' → 'lg'
const mappedSize = computed(() => {
  if (props.size === 'small') return 'sm' as const
  if (props.size === 'large') return 'lg' as const
  return 'default' as const
})

// Select Button Type
const scrollArea = ref<HTMLElement | null>(null)
const contentArea = ref()

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
  const step = 100
  scrollArea.value.scrollBy({
    left: direction === 'prev' ? -step : step,
    behavior: 'smooth',
  })
}

watch([width, height], () => {
  // checkScrollPosition handled by useScroll
})
</script>

<template>
  <!-- Drop mode: DropdownMenu -->
  <slot
    v-if="type === 'drop'"
    name="target"
    v-bind="{ toggle, prefixIcon, suffixIcon, currentLabel, current, overlayVisible }"
  >
    <DropdownMenu v-model:open="overlayVisible">
      <DropdownMenuTrigger as-child>
        <div :class="['-my-1 py-1', $attrs.class]" @click="toggle">
          <Button
            :rounded="rounded"
            :text="text"
            :variant="severity === 'secondary' ? 'secondary' : 'default'"
            :size="mappedSize"
            class="w-full whitespace-nowrap"
          >
            <slot name="prefix">
              <span v-if="prefixIcon" class="size-4 text-mm-muted-fg">
                <component :is="prefixIcon" />
              </span>
            </slot>
            <span class="flex-1 overflow-scroll text-right scrollbar-none">
              <slot name="label">{{ currentLabel }}</slot>
            </span>
            <slot name="suffix">
              <ChevronDown class="size-4 text-mm-muted-fg mm-transition" :class="{ 'rotate-180': overlayVisible }" />
            </slot>
          </Button>
        </div>
      </DropdownMenuTrigger>
      <DropdownMenuContent class="w-[var(--reka-dropdown-menu-trigger-width)] min-w-[8rem]">
        <DropdownMenuItem
          v-for="item in items"
          :key="item.value"
          class="justify-between"
          @select="item.command?.()"
        >
          <slot name="item" :item="item">
            <span>{{ item.label }}</span>
            <Check v-if="current === item.value" class="size-4 text-mm-accent" />
          </slot>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </slot>

  <!-- Button mode: Segmented buttons -->
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
            :active="current === item.value"
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

  <!-- Mobile: Sheet (bottom drawer) -->
  <Sheet v-if="isMobile" v-model:open="visible">
    <SheetContent side="bottom" class="h-auto max-h-[80%]">
      <SheetHeader class="sr-only">
        <SheetTitle>Menu</SheetTitle>
      </SheetHeader>
      <div class="h-full overflow-scroll scrollbar-none">
        <button
          v-for="item in items"
          :key="item.value"
          class="flex w-full items-center justify-between rounded-mm-ctl px-4 py-3 text-left mm-transition hover:bg-mm-surface-hover"
          @click="item.command?.(); visible = false"
        >
          <span class="overflow-hidden break-words text-mm-fg">{{ item.label }}</span>
          <Check v-if="current === item.value" class="size-4 text-mm-accent" />
        </button>
      </div>
    </SheetContent>
  </Sheet>
</template>
