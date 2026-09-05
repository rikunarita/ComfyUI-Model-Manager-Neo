<template>
  <div
    class="flex h-full w-full select-none flex-col overflow-hidden"
    @contextmenu.prevent="nonContextMenu"
  >
    <div class="flex w-full gap-4 overflow-hidden px-4 pb-4">
      <div :class="['flex gap-4 overflow-hidden', showToolbar || 'flex-1']">
        <div class="flex overflow-hidden">
          <Button
            variant="ghost"
            size="icon-sm"
            :disabled="folderPaths.length < 2"
            @click="handleGoBackParentFolder"
          >
            <ChevronUp class="size-4" />
          </Button>
        </div>

        <ResponseBreadcrumb
          v-show="!showToolbar"
          class="h-10 flex-1"
          :items="breadcrumbItems"
        ></ResponseBreadcrumb>
      </div>

      <div :class="['flex gap-4', showToolbar && 'flex-1']">
        <ResponseInput
          v-model="searchContent"
          :placeholder="$t('searchModels')"
        ></ResponseInput>

        <div
          v-show="showToolbar"
          class="flex flex-1 items-center justify-end gap-2"
        >
          <ResponseSelect
            v-model="sortOrder"
            :items="sortOrderOptions"
          ></ResponseSelect>
          <ResponseSelect
            v-model="cardSizeFlag"
            :items="cardSizeOptions"
          ></ResponseSelect>
        </div>

        <Button
          variant="ghost"
          size="icon-sm"
          @click="toggleToolbar"
        >
          <X v-if="showToolbar" class="size-4" />
          <Menu v-else class="size-4" />
        </Button>
      </div>
    </div>

    <div
      ref="contentContainer"
      class="relative flex-1 overflow-hidden px-2"
      @contextmenu.stop.prevent=""
    >
      <ResponseScroll :items="renderedList" :item-size="itemSize">
        <template #item="{ item }">
          <div
            class="grid h-full justify-center"
            :style="{
              gridTemplateColumns: `repeat(auto-fit, ${cardSize.width}px)`,
              columnGap: `${gutter.x}px`,
              rowGap: `${gutter.y}px`,
            }"
          >
            <Tooltip
              v-for="rowItem in (item as any).row"
              :key="genModelKey(rowItem)"
              :delay-duration="800"
            >
              <TooltipTrigger as-child>
                <ModelCard
                  :model="rowItem"
                  :style="{
                    width: `${cardSize.width}px`,
                    height: `${cardSize.height}px`,
                  }"
                  @dblclick="openItem(rowItem, $event)"
                  @contextmenu.stop.prevent="openItemContext(rowItem, $event)"
                />
              </TooltipTrigger>
              <TooltipContent
                v-if="folderPaths.length >= 2"
                side="top"
                class="max-w-[32rem]"
                :style="{ zIndex: 2100 }"
              >
                {{ getFullPath(rowItem) }}
              </TooltipContent>
            </Tooltip>
            <div class="col-span-full"></div>
          </div>
        </template>
      </ResponseScroll>
    </div>

    <div class="flex justify-between px-4 py-2 text-sm">
      <div></div>
      <div></div>
    </div>

    <!-- Context Menu (reka-ui DropdownMenu) -->
    <DropdownMenu v-model:open="contextMenuVisible">
      <DropdownMenuContent>
        <DropdownMenuItem
          v-for="item in contextItems"
          :key="item.label"
          @select="item.command"
        >
          {{ item.label }}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>

<script setup lang="ts">
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { ChevronUp, Menu, X } from '@lucide/vue'
import { useElementSize } from '@vueuse/core'
import ModelCard from 'components/ModelCard.vue'
import ResponseBreadcrumb from 'components/ResponseBreadcrumb.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
} from 'components/ui/dropdown-menu'
import { useConfig } from 'hooks/config'
import { type ModelTreeNode, useModelExplorer } from 'hooks/explorer'
import { chunk } from 'es-toolkit'
import { genModelKey } from 'utils/model'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const gutter = {
  x: 4,
  y: 32,
}

const {
  dataTreeList,
  folderPaths,
  findFolder,
  openFolder,
  openModelDetail,
  getFullPath,
} = useModelExplorer()
const { cardSize, cardSizeMap, cardSizeFlag, dialog: settings } = useConfig()

// folderPaths を BreadcrumbItem[] に変換
const breadcrumbItems = computed(() => {
  return folderPaths.value.map((folder) => ({
    label: folder.name,
    command: () => {
      const index = folderPaths.value.findIndex(
        (f) => f.name === folder.name && f.pathIndex === folder.pathIndex
      )
      if (index >= 0) {
        folderPaths.value.splice(index + 1)
      }
    },
  }))
})

const showToolbar = ref(false)
const toggleToolbar = () => {
  showToolbar.value = !showToolbar.value
}

const contentContainer = ref<HTMLElement | null>(null)
const contentSize = useElementSize(contentContainer)

const itemSize = computed(() => {
  return cardSize.value.height + gutter.y
})

const cols = computed(() => {
  const containerWidth = contentSize.width.value + gutter.x
  const itemWidth = cardSize.value.width + gutter.x

  return Math.max(1, Math.floor(containerWidth / itemWidth))
})

const searchContent = ref<string>()

const sortOrder = ref('name')
const sortOrderOptions = ref(
  ['name', 'size', 'created', 'modified'].map((key) => {
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

const currentDataList = computed(() => {
  let renderedList = dataTreeList.value
  for (const folderItem of folderPaths.value) {
    const found = findFolder(renderedList, {
      basename: folderItem.name,
      pathIndex: folderItem.pathIndex,
    })
    renderedList = found?.children || []
  }

  const filter = searchContent.value?.toLowerCase().trim() ?? ''
  if (filter) {
    const filterItems: ModelTreeNode[] = []

    const searchList = [...renderedList]

    while (searchList.length) {
      const item = searchList.pop()!
      const children = (item as any).children ?? []
      searchList.push(...children)

      const matchSubFolder = `${item.subFolder}/`.toLowerCase().includes(filter)
      const matchName = item.basename.toLowerCase().includes(filter)

      if (matchSubFolder || matchName) {
        filterItems.push(item)
      }
    }

    renderedList = filterItems
  }

  if (folderPaths.value.length > 1) {
    const folderItems: ModelTreeNode[] = []
    const modelItems: ModelTreeNode[] = []

    for (const item of renderedList) {
      if (item.isFolder) {
        folderItems.push(item)
      } else {
        modelItems.push(item)
      }
    }

    folderItems.sort((a, b) => {
      return a.basename.localeCompare(b.basename)
    })
    modelItems.sort((a, b) => {
      const sortFieldMap = {
        name: 'basename',
        size: 'sizeBytes',
        created: 'createdAt',
        modified: 'updatedAt',
      }
      const sortField = (sortFieldMap as Record<string, keyof ModelTreeNode>)[sortOrder.value]

      const aValue = a[sortField]
      const bValue = b[sortField]

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        return aValue.localeCompare(bValue)
      }
      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return aValue - bValue
      }
      return 0
    })
    renderedList = [...folderItems, ...modelItems]
  }

  return renderedList
})

const renderedList = computed(() => {
  return chunk(currentDataList.value, cols.value).map((row) => {
    return { key: row.map((o) => o.basename).join('#'), row }
  })
})

const cardSizeOptions = computed(() => {
  const customSize = 'size.custom'

  const customOptionMap = {
    ...cardSizeMap.value,
    [customSize]: 'custom',
  }

  return Object.keys(customOptionMap).map((key) => {
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

// Context menu state
interface ContextMenuItem {
  label: string
  icon?: string
  command: () => void
}

const contextMenuVisible = ref(false)
const contextItems = ref<ContextMenuItem[]>([])

const openItem = (item: ModelTreeNode, e: Event) => {
  contextMenuVisible.value = false
  if (item.isFolder) {
    searchContent.value = undefined
    openFolder(item)
  } else {
    openModelDetail(item)
  }
}

const openItemContext = (item: ModelTreeNode, e: Event) => {
  if (folderPaths.value.length < 2) {
    return
  }

  contextItems.value = [
    {
      label: t('open'),
      icon: 'pi pi-folder-open',
      command: () => {
        openItem(item, e)
      },
    },
  ]

  contextMenuVisible.value = true
}

const nonContextMenu = (e: Event) => {
  contextMenuVisible.value = false
}

const handleGoBackParentFolder = () => {
  folderPaths.value.pop()
}
</script>
