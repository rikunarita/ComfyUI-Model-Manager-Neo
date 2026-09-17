<template>
  <div ref="contentContainer" class="flex h-full flex-col gap-4 overflow-hidden">
    <div class="grid grid-cols-1 justify-center gap-4 px-8" :style="$content_lg(contentStyle)">
      <div ref="toolbarContainer" class="col-span-full">
        <div :class="['flex gap-4', $toolbar_2xl('flex-row', 'flex-col')]">
          <div class="flex-1">
            <ResponseInput
              v-model="searchContent"
              :placeholder="$t('searchModels')"
              :allow-clear="true"
              suffix-icon="pi pi-search"
            ></ResponseInput>
          </div>

          <div class="flex items-center justify-between gap-4 overflow-hidden">
            <ResponseSelect
              v-model="currentType"
              class="flex-1"
              :items="typeOptions"
            ></ResponseSelect>
            <ResponseSelect
              v-model="sortOrder"
              class="flex-1"
              :items="sortOrderOptions"
            ></ResponseSelect>
            <ResponseSelect
              v-model="cardSizeFlag"
              class="flex-1"
              :items="cardSizeOptions"
            ></ResponseSelect>
            <Button
              variant="secondary"
              size="icon"
              :class="
                selection.state.enabled && 'border-mm-accent/50 bg-mm-accent/20 text-mm-accent'
              "
              :title="$t('selectFiles')"
              :aria-label="$t('selectFiles')"
              :aria-pressed="selection.state.enabled"
              @click="toggleSelectMode"
            >
              <ListChecks class="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>

    <ResponseScroll :items="list" :item-size="itemSize" class="h-full flex-1">
      <template #item="{ item }">
        <div class="grid grid-cols-1 justify-center gap-8 px-8" :style="contentStyle">
          <template v-for="model in (item as any).row" :key="genModelKey(model)">
            <Tooltip :delay-duration="800">
              <TooltipTrigger as-child>
                <ModelCard
                  :model="model"
                  :width="cardSize.width"
                  :selectable="selection.state.enabled"
                  :selected="isSelected(model)"
                  :style="{
                    width: `${cardSize.width}px`,
                    height: `${cardSize.height}px`,
                  }"
                  class="group/card cursor-pointer p-0!"
                  @click="handleCardClick(model)"
                  @toggle="selection.toggle(genModelKey(model))"
                >
                  <template #extra>
                    <CardHoverActions :model="model" />
                  </template>
                </ModelCard>
              </TooltipTrigger>
              <TooltipContent side="top" class="max-w-lg">
                {{ getFullPath(model) }}
              </TooltipContent>
            </Tooltip>
          </template>
          <div class="col-span-full"></div>
        </div>
      </template>

      <template #empty>
        <div class="flex flex-col items-center gap-4 pt-20 opacity-70">
          <!-- BUG FIX: `pi pi-box` rendered empty (PrimeIcons removed). -->
          <Box class="size-10 opacity-60" />
          <div class="text-lg font-bold select-none">{{ $t('noModelsFound') }}</div>
        </div>
      </template>
    </ResponseScroll>

    <!-- Bulk actions for the selection mode (shared with the folder view) -->
    <SelectionBulkBar v-if="selection.state.enabled && selectionCount > 0" :tree="flatModels" />
  </div>
</template>

<script setup lang="ts" name="manager-dialog">
import { Box, ListChecks } from '@lucide/vue'
import { useElementSize, refDebounced } from '@vueuse/core'
import { chunk } from 'es-toolkit'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import CardHoverActions from 'components/CardHoverActions.vue'
import ModelCard from 'components/ModelCard.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import SelectionBulkBar from 'components/SelectionBulkBar.vue'
import { Button } from 'components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { useConfig } from 'hooks/config'
import { useContainerQueries } from 'hooks/container'
import { type ModelTreeNode } from 'hooks/explorer'
import { useGridSelectOptions } from 'hooks/gridOptions'
import { useModels } from 'hooks/model'
import { useModelDetail } from 'hooks/modelDetail'
import { isModelStarred } from 'hooks/stars'
import { useSelection } from 'hooks/zipnn'
import { type Model } from 'types/typings'
import { genModelKey } from 'utils/model'

const { isMobile, gutter, cardSize } = useConfig()

const { data, visibleTypes, getFullPath } = useModels()
const { openModelDetail } = useModelDetail()
const { t } = useI18n()

const toolbarContainer = ref<HTMLElement | null>(null)
const { $2xl: $toolbar_2xl } = useContainerQueries(toolbarContainer)

const contentContainer = ref<HTMLElement | null>(null)
const { $lg: $content_lg } = useContainerQueries(contentContainer)

const searchContent = ref<string>()
// Optimization B-3: the grid filter+sort is O(n log n); running it on every
// keystroke of a large library stalls input. 150 ms of debounce keeps the
// search feeling instant while collapsing bursts into one recompute.
const debouncedSearch = refDebounced(searchContent, 150)

const allType = '__all__'
const currentType = ref(allType)
const typeOptions = computed(() => {
  return [allType, ...visibleTypes()].map(type => {
    return {
      label: type === allType ? t('allTypes') : type,
      value: type,
      command: () => {
        currentType.value = type
      },
    }
  })
})

const { sortOrder, sortOrderOptions, cardSizeOptions, cardSizeFlag, compareRecent } =
  useGridSelectOptions()

const itemSize = computed(() => {
  let itemHeight = cardSize.value.height
  let itemGutter = gutter
  if (isMobile.value) {
    const baseSize = 16
    itemHeight = window.innerWidth - baseSize * 2 * 2
    itemGutter = baseSize * 2
  }
  return itemHeight + itemGutter
})

const { width } = useElementSize(contentContainer)

const cols = computed(() => {
  if (isMobile.value) {
    return 1
  }
  const containerWidth = width.value
  const itemWidth = cardSize.value.width
  return Math.floor((containerWidth - gutter) / (itemWidth + gutter))
})

const list = computed(() => {
  const mergedList = Object.values(data.value).flat()
  const pureModels = mergedList.filter(item => {
    return !item.isFolder
  })

  function buildRegex(raw: string): RegExp {
    try {
      // Escape regex specials, then restore * wildcards as .*
      const escaped = raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\\*/g, '.*')
      return new RegExp(escaped, 'i') // case-insensitive
    } catch {
      return new RegExp(raw, 'i')
    }
  }

  const filterList = pureModels.filter(model => {
    const showAllModel = currentType.value === allType
    const matchType = showAllModel || model.type === currentType.value

    const rawFilter = debouncedSearch.value ?? ''
    const tokens = rawFilter.split(/\s+/).filter(Boolean)
    const regexes = tokens.map(buildRegex)

    // Require every token to match either the folder or the name
    const matchesAll = regexes.every(re => re.test(model.subFolder) || re.test(model.basename))

    return matchType && matchesAll
  })

  let sortStrategy: (a: Model, b: Model) => number = () => 0
  switch (sortOrder.value) {
    case 'name':
      sortStrategy = (a, b) => a.basename.localeCompare(b.basename)
      break
    case 'size':
      sortStrategy = (a, b) => b.sizeBytes - a.sizeBytes
      break
    case 'created':
      sortStrategy = (a, b) => b.createdAt - a.createdAt
      break
    case 'modified':
      sortStrategy = (a, b) => b.updatedAt - a.updatedAt
      break
    case 'recent':
      sortStrategy = (a, b) => compareRecent(genModelKey(a), genModelKey(b))
      break
    default:
      break
  }

  const sortedList = filterList.sort((a, b) => {
    // Starred models always lead the grid; the chosen sort order decides
    // within equal star state.
    const byStar = Number(isModelStarred(genModelKey(b))) - Number(isModelStarred(genModelKey(a)))
    return byStar || sortStrategy(a, b)
  })

  // Guard: es-toolkit's chunk() throws on a non-positive size (unlike lodash,
  // which returned []). Before the container is measured `cols` can be <= 0;
  // mirror the previous behaviour by rendering no rows in that case.
  if (cols.value < 1) {
    return []
  }

  return chunk(sortedList, cols.value).map(row => {
    return { key: row.map(genModelKey).join(','), row }
  })
})

const contentStyle = computed(() => ({
  gridTemplateColumns: `repeat(auto-fit, ${cardSize.value.width}px)`,
  gap: `${gutter}px`,
  paddingLeft: `1rem`,
  paddingRight: `1rem`,
}))

const selection = useSelection()
const selectionCount = selection.count

const isSelected = (model: Model) => Boolean(selection.state.selected[genModelKey(model)])

const handleCardClick = (model: Model) => {
  if (selection.state.enabled) {
    selection.toggle(genModelKey(model))
    return
  }
  openModelDetail(model)
}

const toggleSelectMode = () => {
  if (selection.state.enabled) selection.exit()
  else selection.enter()
}

/* ---- delta compression (exactly two plain .safetensors models selected) -- */

/** Selection-key resolution tree for the shared bulk bar (flat model list). */
const flatModels = computed<ModelTreeNode[]>(() => Object.values(data.value).flat())
</script>
