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
                  <template #name>
                    <div v-show="showModelName" class="absolute top-0 size-full p-2">
                      <div class="flex h-full flex-col justify-end text-lg">
                        <div class="text-shadow line-clamp-3 font-bold break-all">
                          {{ model.basename }}
                        </div>
                      </div>
                    </div>
                  </template>

                  <template #extra>
                    <!--
                      BUG FIX: the wrapper is `pointer-events-none` (so the
                      invisible buttons never swallow card clicks) but the
                      buttons themselves never re-enabled pointer events, so
                      every press landed on the drag overlay underneath and
                      simply opened the card. The inner column now turns
                      pointer-events back on exactly while the card is hovered.
                    -->
                    <div
                      v-show="showModelName"
                      class="pointer-events-none absolute top-12 right-2 opacity-0 duration-300 group-hover/card:pointer-events-auto group-hover/card:opacity-100 group-data-[dragging=true]/card:pointer-events-none! group-data-[dragging=true]/card:opacity-0!"
                    >
                      <div class="flex flex-col gap-2">
                        <Button
                          variant="secondary"
                          size="icon-sm"
                          class="rounded-full"
                          :title="$t('addNode')"
                          :aria-label="$t('addNode')"
                          @click.stop="addModelNode(model)"
                        >
                          <Plus class="size-4" />
                        </Button>
                        <Button
                          variant="secondary"
                          size="icon-sm"
                          class="rounded-full"
                          :title="$t('copyNode')"
                          :aria-label="$t('copyNode')"
                          @click.stop="copyModelNode(model)"
                        >
                          <Copy class="size-4" />
                        </Button>
                        <Button
                          v-show="model.preview"
                          variant="secondary"
                          size="icon-sm"
                          class="rounded-full"
                          :title="$t('loadWorkflow')"
                          :aria-label="$t('loadWorkflow')"
                          @click.stop="loadPreviewWorkflow(model)"
                        >
                          <Workflow class="size-4" />
                        </Button>
                        <Button
                          variant="secondary"
                          size="icon-sm"
                          class="rounded-full"
                          :title="$t('openModelPage')"
                          :aria-label="$t('openModelPage')"
                          @click.stop="openModelPage(model)"
                        >
                          <ExternalLink class="size-4" />
                        </Button>
                      </div>
                    </div>
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

    <!-- Bulk actions for the selection mode -->
    <div
      v-if="selection.state.enabled && selectionCount > 0"
      class="mm-glass-light mm-scope mx-8 mb-2 flex items-center justify-between gap-4 rounded-mm-ctl border border-mm-border px-4 py-2"
    >
      <span class="text-sm text-mm-muted-fg tabular-nums">
        {{ $t('selectedCount', { count: selectionCount }) }}
      </span>
      <div class="flex items-center gap-2">
        <Button variant="secondary" size="sm" @click="addSelectedToWorkflow">
          <Plus class="size-4" />
          {{ $t('addToWorkflow') }}
        </Button>
        <Button variant="destructive" size="sm" @click="deleteSelected">
          <Trash2 class="size-4" />
          {{ $t('delete') }}
        </Button>
        <Button variant="ghost" size="sm" @click="selection.clear()">
          {{ $t('clearSelection') }}
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts" name="manager-dialog">
import { Box, Copy, ExternalLink, ListChecks, Plus, Trash2, Workflow } from '@lucide/vue'
import { useElementSize, refDebounced } from '@vueuse/core'
import { chunk } from 'es-toolkit'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ModelCard from 'components/ModelCard.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { configSetting, useConfig } from 'hooks/config'
import { useContainerQueries } from 'hooks/container'
import { useModelNodeAction, useModels } from 'hooks/model'
import { useToast } from 'hooks/toast'
import { useSelection } from 'hooks/zipnn'
import { app } from 'scripts/comfyAPI'
import { type Model } from 'types/typings'
import { genModelKey } from 'utils/model'

const { isMobile, gutter, cardSize, cardSizeMap, cardSizeFlag, dialog: settings } = useConfig()

const { data, folders, openModelDetail, getFullPath, remove } = useModels()
const { t } = useI18n()
const { toast, confirm } = useToast()

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
  const excludeModelTypes = app.ui?.settings.getSettingValue<string>(
    configSetting.excludeModelTypes,
  )
  const customBlackList =
    excludeModelTypes
      ?.split(',')
      .map((type: string) => type.trim())
      .filter(Boolean) ?? []
  return [
    allType,
    ...Object.keys(folders.value).filter(folder => !customBlackList.includes(folder)),
  ].map(type => {
    return {
      label: type === allType ? t('allTypes') : type,
      value: type,
      command: () => {
        currentType.value = type
      },
    }
  })
})

const sortOrder = ref('name')
const sortOrderOptions = ref(
  ['name', 'size', 'created', 'modified'].map(key => {
    return {
      label: t(`sort.${key}`),
      value: key,
      icon: key === 'name' ? 'pi pi-sort-alpha-down' : 'pi pi-sort-amount-down',
      command: () => {
        sortOrder.value = key
      },
    }
  }),
)

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
    default:
      break
  }

  const sortedList = filterList.sort(sortStrategy)

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

const cardSizeOptions = computed(() => {
  const customSize = 'size.custom'

  const customOptionMap = {
    ...cardSizeMap.value,
    [customSize]: 'custom',
  }

  return Object.keys(customOptionMap).map(key => {
    return {
      label: t(key),
      value: key,
      command: () => {
        if (key === customSize) {
          settings.showCardSizeSetting()
        } else {
          cardSizeFlag.value = key
        }
      },
    }
  })
})

const showModelName = computed(() => {
  return cardSize.value.width > 120 && cardSize.value.height > 160
})

const { addModelNode, copyModelNode, loadPreviewWorkflow } = useModelNodeAction()
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

const selectedModels = () =>
  list.value.flatMap(row => (row as any).row).filter((m: Model) => isSelected(m))

const addSelectedToWorkflow = () => {
  for (const model of selectedModels()) addModelNode(model)
}

const deleteSelected = () => {
  const models = selectedModels()
  confirm.require({
    message: t('deleteAsk', [t('model').toLowerCase() + ` (${models.length})`]),
    header: 'Danger',
    icon: 'pi pi-info-circle',
    rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
    acceptProps: { label: t('delete'), severity: 'danger' },
    accept: async () => {
      for (const model of models) await remove(model)
      selection.clear()
    },
    reject: () => {},
  })
}

const openModelPage = (model: Model) => {
  const page = (model as Model & { modelPage?: string }).modelPage
  if (!page) {
    toast.add({ severity: 'info', summary: t('noModelPage'), life: 4000 })
    return
  }
  window.open(page, '_blank')
}
</script>
