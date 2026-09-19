<template>
  <div ref="contentContainer" class="flex h-full flex-col gap-4 overflow-hidden">
    <ViewToolbar
      v-model:search="searchContent"
      v-model:sort-order="sortOrder"
      v-model:current-type="currentType"
      mode="flat"
      :sort-order-options="sortOrderOptions"
      :type-options="typeOptions"
      :selection-enabled="selection.state.enabled"
      :get-query="currentQuery"
      @toggle-select="toggleSelectMode"
    />

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
    <!--
      The flat view's selection is model-only: the folder-only extras (folder
      star toggle, ZipNN batch / folder upload buttons) must not render there
      - with the default `folder-actions` the star button showed up in the
      flat bar and did nothing when clicked (its subject list is always
      empty outside the folder view).
    -->
    <SelectionBulkBar
      v-if="selection.state.enabled && selectionCount > 0"
      :tree="flatModels"
      :folder-actions="false"
    />
  </div>
</template>

<script setup lang="ts" name="manager-dialog">
import { Box } from '@lucide/vue'
import { useElementSize, refDebounced } from '@vueuse/core'
import { chunk } from 'es-toolkit'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import CardHoverActions from 'components/CardHoverActions.vue'
import ModelCard from 'components/ModelCard.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import SelectionBulkBar from 'components/SelectionBulkBar.vue'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import ViewToolbar from 'components/ViewToolbar.vue'
import { activeCollection, matchesCollection } from 'hooks/collections'
import { useConfig } from 'hooks/config'
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

const contentContainer = ref<HTMLElement | null>(null)

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

const { sortOrder, sortOrderOptions, compareRecent } = useGridSelectOptions()
/* ---- smart collections ------------------------------------------------- */
const activeCol = computed(() => activeCollection())

const currentQuery = () => ({
  tokens: (searchContent.value ?? '').split(/\s+/).filter(Boolean),
  types: currentType.value !== allType ? [currentType.value] : [],
})

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
    const matchCollection = !activeCol.value || matchesCollection(model, activeCol.value.query)

    const rawFilter = debouncedSearch.value ?? ''
    const tokens = rawFilter.split(/\s+/).filter(Boolean)
    const regexes = tokens.map(buildRegex)

    // Require every token to match either the folder or the name
    const matchesAll = regexes.every(re => re.test(model.subFolder) || re.test(model.basename))

    return matchType && matchesAll && matchCollection
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
