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
import { computed, nextTick, ref, watch } from 'vue'
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
import { buildModelRows, buildSearchTokens, compareText } from 'utils/modelFilter'
import { PERF_PREFIX, perfEnabled, perfRecord, perfTime } from 'utils/perf'

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

/**
 * C1 (Plan §4.8): the search query is compiled into its token regexes ONCE per
 * change instead of once per model per keystroke - a 5,000-model library used
 * to rebuild the same 1-3 `RegExp` objects 5,000 times on every recompute.
 */
const searchTokens = computed(() => buildSearchTokens(debouncedSearch.value))

/** The non-token gates of the filter: model type + the active collection. */
const matchesTypeAndCollection = (model: Model) => {
  const showAllModel = currentType.value === allType
  const matchType = showAllModel || model.type === currentType.value
  return matchType && (!activeCol.value || matchesCollection(model, activeCol.value.query))
}

/** The chosen sort order, as a comparator (C2: the text order goes through the
 *  shared, MEASURED comparator in utils/modelFilter - see the note there for why
 *  the default variant stays on V8's `localeCompare` builtin). */
const sortStrategy = computed<(a: Model, b: Model) => number>(() => {
  switch (sortOrder.value) {
    case 'name':
      return (a, b) => compareText(a.basename, b.basename)
    case 'size':
      return (a, b) => b.sizeBytes - a.sizeBytes
    case 'created':
      return (a, b) => b.createdAt - a.createdAt
    case 'modified':
      return (a, b) => b.updatedAt - a.updatedAt
    case 'recent':
      return (a, b) => compareRecent(genModelKey(a), genModelKey(b))
    default:
      return () => 0
  }
})

/* ---- C5: keystroke -> painted-grid instrumentation (K15) -----------------
 * Recorded only while the instrumentation is switched on (`__mmNeoPerf.enable()`
 * or the `ModelManager.UI.PerfMarks` setting - utils/perf.ts). Disabled, the
 * whole path costs ONE boolean test per call site: no `performance.now()`, no
 * `nextTick`, no `requestAnimationFrame`.
 *
 * `queryToPaint` is the K15 number (the debounced query change -> the frame that
 * shows it); `keystrokeToPaint` additionally includes the 150 ms input debounce
 * of Optimization B-3, and `initialRender` covers manager open -> first non-empty
 * grid paint. The state is declared BEFORE the `list` computed on purpose: the
 * computed writes `recomputeAt`, and a `let` used before its declaration would
 * be a TDZ ReferenceError the moment anything evaluated it during setup.
 */
const openedAt = performance.now()
let keystrokeAt = 0
let recomputeAt = 0
let paintScheduled = false
let initialPaintRecorded = false

const list = computed(() =>
  perfTime(`${PERF_PREFIX}grid.list`, () => {
    if (perfEnabled()) recomputeAt = performance.now()
    const mergedList = Object.values(data.value).flat()
    const byStrategy = sortStrategy.value
    // One pure pipeline (filter -> sort -> chunk) shared with the headless K15
    // harness, so the measurement and the browser run the same code. The
    // non-positive `cols` guard (before the container is measured) lives in
    // `chunkRows`: es-toolkit's chunk() used to THROW there.
    return buildModelRows(mergedList, {
      tokens: searchTokens.value,
      matches: matchesTypeAndCollection,
      compare: (a, b) => {
        // Starred models always lead the grid; the chosen sort order decides
        // within equal star state.
        const byStar =
          Number(isModelStarred(genModelKey(b))) - Number(isModelStarred(genModelKey(a)))
        return byStar || byStrategy(a, b)
      },
      columns: cols.value,
      keyOf: genModelKey,
    })
  }),
)

watch(searchContent, () => {
  if (perfEnabled()) keystrokeAt = performance.now()
})

watch(list, () => {
  if (!perfEnabled() || paintScheduled) return
  paintScheduled = true
  void nextTick(() => {
    if (typeof requestAnimationFrame !== 'function') {
      paintScheduled = false
      return
    }
    requestAnimationFrame(() => {
      paintScheduled = false
      const painted = performance.now()
      if (recomputeAt > 0) perfRecord(`${PERF_PREFIX}grid.queryToPaint`, painted - recomputeAt)
      if (keystrokeAt > 0) perfRecord(`${PERF_PREFIX}grid.keystrokeToPaint`, painted - keystrokeAt)
      if (!initialPaintRecorded && list.value.length > 0) {
        initialPaintRecorded = true
        perfRecord(`${PERF_PREFIX}grid.initialRender`, painted - openedAt)
      }
    })
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
