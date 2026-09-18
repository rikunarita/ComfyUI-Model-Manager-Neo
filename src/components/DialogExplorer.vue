<template>
  <div
    class="flex size-full flex-col overflow-hidden select-none"
    @contextmenu.prevent="nonContextMenu"
  >
    <!--
      LAYOUT FIX (second pass): the folder toolbar now reuses the EXACT same
      responsive pattern as the flat view's toolbar (DialogManager): one
      `flex gap-4` row that a container query flips to `flex-col` below 42 rem,
      the search input inside a `flex-1` wrapper, and the selects as `flex-1`
      siblings of the icon buttons inside a content-sized group. The previous
      attempt wrapped the row and passed `w-36` to the drop selects, but the
      drop-mode button carries `w-full`, which won the cascade - the selects
      stretched to the whole dialog and stacked, so the folder toolbar looked
      nothing like the flat one. Same controls, same order, same look.
    -->
    <div ref="toolbarContainer" class="w-full px-4 pb-4">
      <div :class="['flex gap-4', $toolbar_2xl('flex-row', 'flex-col')]">
        <div class="flex min-w-0 flex-1 items-center gap-4 overflow-hidden">
          <Button
            variant="ghost"
            size="icon-sm"
            class="shrink-0"
            :disabled="folderPaths.length < 2"
            @click="handleGoBackParentFolder"
          >
            <ChevronUp class="size-4" />
          </Button>

          <ResponseBreadcrumb
            class="h-10 min-w-0 flex-1"
            :items="breadcrumbItems"
          ></ResponseBreadcrumb>
        </div>

        <div class="flex-1">
          <ResponseInput
            v-model="searchContent"
            :placeholder="$t('searchModels')"
            :allow-clear="true"
            suffix-icon="pi pi-search"
          ></ResponseInput>
        </div>

        <!--
          View parity with the flat view: the same sort and card-size selects
          live here too (folder view = flat view scoped to one folder, plus
          the folder-only extras). "Add folder" creates a sub-folder inside
          the currently open folder.
        -->
        <div class="flex items-center justify-between gap-4 overflow-hidden">
          <GridCommonControls
            v-model:sort-order="sortOrder"
            :sort-order-options="sortOrderOptions"
            @hygiene="openHygiene"
          />
          <Button
            variant="secondary"
            size="icon"
            :disabled="!currentFolderInfo"
            :title="$t('addFolder')"
            :aria-label="$t('addFolder')"
            @click="openCreateFolder"
          >
            <FolderPlus class="size-4" />
          </Button>
          <Button
            variant="secondary"
            size="icon"
            :class="selection.state.enabled && 'border-mm-accent/50 bg-mm-accent/20 text-mm-accent'"
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
                  :width="cardSize.width"
                  :selectable="selection.state.enabled"
                  :selected="isSelected(rowItem)"
                  :style="{
                    width: `${cardSize.width}px`,
                    height: `${cardSize.height}px`,
                  }"
                  class="group/card cursor-pointer"
                  @click="handleCardClick(rowItem)"
                  @toggle="selection.toggle(genModelKey(rowItem))"
                  @dblclick="openItem(rowItem, $event)"
                  @contextmenu.stop.prevent="openItemContext(rowItem, $event)"
                >
                  <template v-if="!rowItem.isFolder" #extra>
                    <CardHoverActions :model="rowItem" />
                  </template>
                </ModelCard>
              </TooltipTrigger>
              <TooltipContent v-if="folderPaths.length >= 2" side="top" class="max-w-lg">
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

    <!-- Bulk actions for the selection mode -->
    <SelectionBulkBar v-if="selection.state.enabled && selectionCount > 0" :tree="dataTreeList" />

    <!-- Context Menu (reka-ui DropdownMenu, anchored at the right-click point) -->
    <DropdownMenu v-model:open="contextMenuVisible">
      <DropdownMenuContent :reference="contextMenuAnchor" align="start" :side-offset="2">
        <DropdownMenuItem v-for="item in contextItems" :key="item.label" @select="item.command">
          <!--
            BUG FIX: `contextItems` carries an `icon` (declared in the
            ContextMenuItem interface and supplied by openItemContext) but it
            was never rendered, so the right-click menu showed bare text.
            Resolved through the Lucide map like every other icon in Neo.
          -->
          <component
            :is="resolveIcon(item.icon ?? '')"
            v-if="item.icon && resolveIcon(item.icon)"
            class="size-4"
          />
          {{ item.label }}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>

<script setup lang="ts">
import { ChevronUp, FolderPlus, ListChecks } from '@lucide/vue'
import { useElementSize, refDebounced } from '@vueuse/core'
import { chunk } from 'es-toolkit'
import { type ReferenceElement } from 'reka-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import CardHoverActions from 'components/CardHoverActions.vue'
import DialogCreateFolder from 'components/DialogCreateFolder.vue'
import DialogHygiene from 'components/DialogHygiene.vue'
import GridCommonControls from 'components/GridCommonControls.vue'
import ModelCard from 'components/ModelCard.vue'
import ResponseBreadcrumb from 'components/ResponseBreadcrumb.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import SelectionBulkBar from 'components/SelectionBulkBar.vue'
import { Button } from 'components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem } from 'components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { useConfig } from 'hooks/config'
import { useContainerQueries } from 'hooks/container'
import { useDialog } from 'hooks/dialog'
import { type ModelTreeNode, useModelExplorer } from 'hooks/explorer'
import { useGridSelectOptions } from 'hooks/gridOptions'
import { useModelDetail } from 'hooks/modelDetail'
import { isFolderStarred } from 'hooks/stars'
import { useSelection } from 'hooks/zipnn'
import { resolveIcon } from 'utils/iconMap'
import { genModelKey, isBundleFolderName } from 'utils/model'

const { t } = useI18n()
const selection = useSelection()
const selectionCount = selection.count
const dialog = useDialog()

const isSelected = (model: ModelTreeNode) => Boolean(selection.state.selected[genModelKey(model)])

/** Selection kind for the ZipNN bundle exclusion rule. */
const kindOf = (node: ModelTreeNode) =>
  node.isFolder ? (isBundleFolderName(node.basename) ? 'znn-folder' : 'folder') : ('model' as const)

const handleCardClick = (model: ModelTreeNode) => {
  if (selection.state.enabled) {
    selection.toggle(genModelKey(model), kindOf(model))
    return
  }
  // view parity: a plain click on a MODEL card opens its detail dialog exactly
  // like the flat view; folders keep their own double-click navigation
  if (!model.isFolder) openModelDetail(model)
}

const toggleSelectMode = () => {
  if (selection.state.enabled) selection.exit()
  else selection.enter()
}

/* ---- create folder ------------------------------------------------------ */
const openHygiene = () => {
  dialog.open({
    key: 'hygiene',
    title: t('hygiene'),
    content: DialogHygiene,
    defaultSize: { width: 680, height: 520 },
  })
}

const openCreateFolder = () => {
  const info = currentFolderInfo.value
  if (!info) return
  dialog.open({
    key: 'create-folder',
    title: t('addFolder'),
    content: DialogCreateFolder,
    contentProps: { ...info },
    defaultSize: { width: 440, height: 230 },
  })
}

const gutter = {
  x: 4,
  y: 32,
}

const { dataTreeList, folderPaths, findFolder, openFolder, getFullPath } = useModelExplorer()
const { openModelDetail } = useModelDetail()
const { cardSize } = useConfig()

// folderPaths を BreadcrumbItem[] に変換
const breadcrumbItems = computed(() => {
  return folderPaths.value.map(folder => ({
    label: folder.name,
    command: () => {
      const index = folderPaths.value.findIndex(
        f => f.name === folder.name && f.pathIndex === folder.pathIndex,
      )
      if (index >= 0) {
        folderPaths.value.splice(index + 1)
      }
    },
  }))
})

const contentContainer = ref<HTMLElement | null>(null)
const contentSize = useElementSize(contentContainer)

// Same responsive rule as the flat view's toolbar (DialogManager): below a
// 42 rem container the toolbar stacks instead of squeezing its controls.
const toolbarContainer = ref<HTMLElement | null>(null)
const { $2xl: $toolbar_2xl } = useContainerQueries(toolbarContainer)

const itemSize = computed(() => {
  return cardSize.value.height + gutter.y
})

const cols = computed(() => {
  const containerWidth = contentSize.width.value + gutter.x
  const itemWidth = cardSize.value.width + gutter.x

  return Math.max(1, Math.floor(containerWidth / itemWidth))
})

const searchContent = ref<string>()
// Optimization B-3: collapse keystroke bursts into one tree filter pass.
const debouncedSearch = refDebounced(searchContent, 150)

const { sortOrder, sortOrderOptions, compareRecent } = useGridSelectOptions()

/** Depth-first collect of every node matching the search filter. */
const applySearchFilter = (list: ModelTreeNode[], filter: string): ModelTreeNode[] => {
  const filterItems: ModelTreeNode[] = []
  const searchList = [...list]

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
  return filterItems
}

/** Folders first (by name), then models (by the chosen sort key); stars lead. */
const sortFolderContents = (list: ModelTreeNode[]): ModelTreeNode[] => {
  const folderItems: ModelTreeNode[] = []
  const modelItems: ModelTreeNode[] = []

  for (const item of list) {
    if (item.isFolder) folderItems.push(item)
    else modelItems.push(item)
  }

  // Starred entries always lead their group; the chosen sort order decides
  // within equal star state (Array#sort is stable).
  const starFirst = (a: ModelTreeNode, b: ModelTreeNode) =>
    Number(isFolderStarred(genModelKey(b))) - Number(isFolderStarred(genModelKey(a)))

  folderItems.sort((a, b) => starFirst(a, b) || a.basename.localeCompare(b.basename))
  modelItems.sort((a, b) => {
    const byStar = starFirst(a, b)
    if (byStar) return byStar
    if (sortOrder.value === 'recent') {
      return compareRecent(genModelKey(a), genModelKey(b))
    }
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
  return [...folderItems, ...modelItems]
}

const currentDataList = computed(() => {
  let renderedList = dataTreeList.value
  for (const folderItem of folderPaths.value) {
    const found = findFolder(renderedList, {
      basename: folderItem.name,
      pathIndex: folderItem.pathIndex,
    })
    renderedList = found?.children || []
  }

  const filter = debouncedSearch.value?.toLowerCase().trim() ?? ''
  if (filter) {
    renderedList = applySearchFilter(renderedList, filter)
  }

  if (folderPaths.value.length > 1) {
    return sortFolderContents(renderedList)
  }
  // Root level (the model-type folders): starred folders lead here too.
  return [...renderedList].sort(
    (a, b) => Number(isFolderStarred(genModelKey(b))) - Number(isFolderStarred(genModelKey(a))),
  )
})

const renderedList = computed(() => {
  return chunk(currentDataList.value, cols.value).map(row => {
    return { key: row.map(o => o.basename).join('#'), row }
  })
})

/**
 * Where "Add folder" creates into: the folder currently open in the
 * breadcrumb (root level disables the button - a type root is chosen by
 * navigating into it first).
 */
const currentFolderInfo = computed(() => {
  const paths = folderPaths.value
  if (paths.length < 2) return null
  const last = paths[paths.length - 1]
  return {
    type: paths[1].name,
    pathIndex: last.pathIndex,
    subFolder: paths
      .slice(2)
      .map(p => p.name)
      .filter(Boolean)
      .join('/'),
  }
})

// Context menu state
interface ContextMenuItem {
  label: string
  icon?: string
  command: () => void
}

const contextMenuVisible = ref(false)
const contextItems = ref<ContextMenuItem[]>([])

const openItem = (item: ModelTreeNode, _e?: Event) => {
  contextMenuVisible.value = false
  if (item.isFolder) {
    searchContent.value = undefined
    openFolder(item)
  } else {
    openModelDetail(item)
  }
}

// Virtual anchor for the context menu. reka-ui positions the dropdown
// against this "reference" element; without one the popper floats at the
// top-left corner of the viewport. This restores the cursor-positioned
// behaviour the original PrimeVue ContextMenu had.
const contextMenuAnchor = ref<ReferenceElement>()

const openItemContext = (item: ModelTreeNode, e: MouseEvent) => {
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

  const { clientX, clientY } = e
  contextMenuAnchor.value = {
    getBoundingClientRect: () => new DOMRect(clientX, clientY, 0, 0),
  }

  contextMenuVisible.value = true
}

const nonContextMenu = () => {
  contextMenuVisible.value = false
}

const handleGoBackParentFolder = () => {
  folderPaths.value.pop()
}
</script>
