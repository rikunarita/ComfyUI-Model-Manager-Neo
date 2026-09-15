<template>
  <div
    class="flex size-full flex-col overflow-hidden select-none"
    @contextmenu.prevent="nonContextMenu"
  >
    <div class="flex w-full gap-4 overflow-hidden px-4 pb-4">
      <div class="flex flex-1 gap-4 overflow-hidden">
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

        <ResponseBreadcrumb class="h-10 flex-1" :items="breadcrumbItems"></ResponseBreadcrumb>
      </div>

      <div class="flex gap-4">
        <ResponseInput v-model="searchContent" :placeholder="$t('searchModels')"></ResponseInput>

        <!--
          "Add folder": creates a sub-folder inside the currently open folder.
          The former hamburger/"filter" toggle and its sort/card-size toolbar
          were removed on purpose - folder navigation makes the extra filter
          surface redundant, and the card size stays adjustable in the flat
          view.
        -->
        <Button
          variant="ghost"
          size="icon"
          :disabled="!currentFolderInfo"
          :title="$t('addFolder')"
          :aria-label="$t('addFolder')"
          @click="openCreateFolder"
        >
          <FolderPlus class="size-4" />
        </Button>
        <Button
          variant="ghost"
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
                  @click="handleCardClick(rowItem)"
                  @toggle="selection.toggle(genModelKey(rowItem))"
                  @dblclick="openItem(rowItem, $event)"
                  @contextmenu.stop.prevent="openItemContext(rowItem, $event)"
                />
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
    <div
      v-if="selection.state.enabled && selectionCount > 0"
      class="mm-glass-light mm-scope mx-4 mb-2 flex items-center justify-between gap-4 rounded-mm-ctl border border-mm-border px-4 py-2"
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
        <!--
          ZipNN batch (folder selection): the shipped SVG artwork *is* the
          button, exactly like the model-card call-to-action - same
          confirmation, same inverted colours for `*_ZNN` bundles, same
          progress state (spinner while the batch task runs).
        -->
        <button
          v-if="selectedFolderNodes.length > 0"
          type="button"
          class="mm-zipnn-button size-9 shrink-0 rounded-mm-ctl"
          :title="batchLabel"
          :aria-label="batchLabel"
          :disabled="zipnnRunning"
          @click="requestBatch"
        >
          <Loader2 v-if="zipnnRunning" class="size-5 animate-spin text-mm-accent" />
          <img
            v-else
            :src="zipnnIcon"
            alt=""
            class="size-full rounded-mm-ctl"
            :class="batchInverted && 'hue-rotate-180 invert'"
          />
        </button>
        <!-- Delta compression: exactly two plain .safetensors models selected -->
        <Button
          v-if="deltaPair"
          variant="secondary"
          size="sm"
          :title="$t('zipnnDeltaCompress')"
          @click="openDeltaDialog"
        >
          <GitCompareArrows class="size-4" />
          {{ $t('zipnnDeltaCompress') }}
        </Button>
        <!-- Star toggle for the selected folders (icon only, per spec) -->
        <Button
          v-if="selectedFolderNodes.length > 0"
          variant="ghost"
          size="icon-sm"
          :title="allSelectedFoldersStarred ? $t('unstar') : $t('star')"
          :aria-label="allSelectedFoldersStarred ? $t('unstar') : $t('star')"
          @click="starSelectedFolders"
        >
          <Star
            class="size-4"
            :class="allSelectedFoldersStarred ? 'fill-current text-mm-warning' : ''"
          />
        </Button>
        <Button variant="ghost" size="sm" @click="selection.clear()">
          {{ $t('clearSelection') }}
        </Button>
      </div>
    </div>

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
import {
  ChevronUp,
  FolderPlus,
  GitCompareArrows,
  ListChecks,
  Loader2,
  Plus,
  Star,
  Trash2,
} from '@lucide/vue'
import { useElementSize, refDebounced } from '@vueuse/core'
import { chunk } from 'es-toolkit'
import { type ReferenceElement } from 'reka-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import DialogCreateFolder from 'components/DialogCreateFolder.vue'
import DialogZipnnDelta from 'components/DialogZipnnDelta.vue'
import ModelCard from 'components/ModelCard.vue'
import ResponseBreadcrumb from 'components/ResponseBreadcrumb.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem } from 'components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { useConfig } from 'hooks/config'
import { useDialog } from 'hooks/dialog'
import { type ModelTreeNode, useModelExplorer } from 'hooks/explorer'
import { genModelFullName, useModelNodeAction, useModels } from 'hooks/model'
import { applyFolderStars, isFolderStarred } from 'hooks/stars'
import { useToast } from 'hooks/toast'
import { queueZipnnBatches, useSelection, zipnnState } from 'hooks/zipnn'
import { resolveIcon } from 'utils/iconMap'
import { assetUrl } from 'utils/media'
import { genModelKey, isZnnFolderName } from 'utils/model'

const { t } = useI18n()
const { toast, confirm } = useToast()
const selection = useSelection()
const selectionCount = selection.count
const { addModelNode } = useModelNodeAction()
const { remove } = useModels()
const dialog = useDialog()

const isSelected = (model: ModelTreeNode) => Boolean(selection.state.selected[genModelKey(model)])

/** Selection kind for the ZipNN bundle exclusion rule. */
const kindOf = (node: ModelTreeNode) =>
  node.isFolder ? (isZnnFolderName(node.basename) ? 'znn-folder' : 'folder') : ('model' as const)

const handleCardClick = (model: ModelTreeNode) => {
  if (selection.state.enabled) selection.toggle(genModelKey(model), kindOf(model))
}

const toggleSelectMode = () => {
  if (selection.state.enabled) selection.exit()
  else selection.enter()
}

/* ---- selected nodes (a selection can span folders AND models) ---------- */
const findNodeByKey = (list: ModelTreeNode[], key: string): ModelTreeNode | undefined => {
  for (const node of list) {
    if (genModelKey(node) === key) return node
    if (node.children?.length) {
      const found = findNodeByKey(node.children, key)
      if (found) return found
    }
  }
  return undefined
}

const selectedNodes = () =>
  Object.keys(selection.state.selected)
    .map(key => findNodeByKey(dataTreeList.value, key))
    .filter((n): n is ModelTreeNode => Boolean(n))

const collectFolderModels = (node: ModelTreeNode): ModelTreeNode[] => {
  const models: ModelTreeNode[] = []
  for (const child of node.children ?? []) {
    if (child.isFolder) models.push(...collectFolderModels(child))
    else models.push(child)
  }
  return models
}

const selectedFolderNodes = computed(() =>
  // type-root folders (the library's top level) are never batch/star targets
  selectedNodes().filter(n => n.isFolder && !(n.basename === n.type && !n.subFolder)),
)
const selectedModelNodes = computed(() => selectedNodes().filter(n => !n.isFolder))

/**
 * BUG FIX: "Add to workflow" on a folder selection used to add NOTHING - the
 * old helper filtered folders out and only looked at the current view, so the
 * models inside a selected folder were never expanded into nodes.
 */
const addSelectedToWorkflow = () => {
  const models: ModelTreeNode[] = []
  for (const node of selectedNodes()) {
    if (node.isFolder) models.push(...collectFolderModels(node))
    else models.push(node)
  }
  for (const model of models) addModelNode(model)
  if (models.length > 1) {
    toast.add({
      severity: 'success',
      summary: t('nodeAdded'),
      detail: `${models.length}`,
      life: 2500,
    })
  }
}

/**
 * BUG FIX: folder deletion never reached the backend (folders were filtered
 * out of the selection, so "Delete" silently did nothing for them). The
 * delete route now removes directories recursively.
 */
const deleteSelected = () => {
  const nodes = selectedNodes()
  const modelCount = nodes.filter(n => !n.isFolder).length
  const folderCount = nodes.length - modelCount
  const subject =
    folderCount > 0
      ? t('deleteAskSubjectMixed', { models: modelCount, folders: folderCount })
      : `${t('model').toLowerCase()} (${modelCount})`
  confirm.require({
    message: t('deleteAsk', [subject]),
    header: 'Danger',
    icon: 'pi pi-info-circle',
    rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
    acceptProps: { label: t('delete'), severity: 'danger' },
    accept: async () => {
      for (const node of nodes) await remove(node)
      selection.clear()
    },
    reject: () => {},
  })
}

/* ---- ZipNN batch (folder selection) ------------------------------------ */
const zipnnIcon = assetUrl('zipnn-button')
const zipnnRunning = computed(
  () =>
    zipnnState.active &&
    selectedFolderNodes.value.some(n => genModelKey(n) === zipnnState.targetKey),
)
const batchInverted = computed(
  () =>
    selectedFolderNodes.value.length > 0 &&
    selectedFolderNodes.value.every(n => isZnnFolderName(n.basename)),
)
const batchLabel = computed(() =>
  batchInverted.value ? t('zipnnBatchDecompress') : t('zipnnBatchCompress'),
)

const requestBatch = () => {
  const folders = selectedFolderNodes.value
  if (folders.length === 0) return
  const decompressing = batchInverted.value
  const names = folders.map(f => f.basename).join(', ')
  confirm.require({
    message: decompressing
      ? t('zipnnBatchConfirmDecompress', { name: names })
      : t('zipnnBatchConfirmCompress', { name: names }),
    header: decompressing ? t('zipnnBatchDecompress') : t('zipnnBatchCompress'),
    icon: 'pi pi-info-circle',
    rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
    acceptProps: { label: decompressing ? t('zipnnBatchDecompress') : t('zipnnBatchCompress') },
    accept: () => {
      queueZipnnBatches(
        decompressing ? 'decompress' : 'compress',
        folders.map(f => ({
          folder: { type: f.type, pathIndex: f.pathIndex, folder: genModelFullName(f) },
          key: genModelKey(f),
        })),
      )
    },
    reject: () => {},
  })
}

/* ---- delta compression (exactly two plain models selected) ------------- */
const deltaPair = computed(() => {
  const models = selectedModelNodes.value.filter(
    m => m.extension === '.safetensors' && !m.basename.endsWith('.znn'),
  )
  return models.length === 2 ? models : null
})

const openDeltaDialog = () => {
  const pair = deltaPair.value
  if (!pair) return
  dialog.open({
    key: 'zipnn-delta',
    title: t('zipnnDeltaCompress'),
    content: DialogZipnnDelta,
    contentProps: { models: pair },
    defaultSize: { width: 480, height: 280 },
  })
}

/* ---- star toggle for the selected folders ------------------------------ */
const allSelectedFoldersStarred = computed(
  () =>
    selectedFolderNodes.value.length > 0 &&
    selectedFolderNodes.value.every(n => isFolderStarred(genModelKey(n))),
)
const starSelectedFolders = () => {
  applyFolderStars(selectedFolderNodes.value.map(n => genModelKey(n)))
}

/* ---- create folder ------------------------------------------------------ */
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

const { dataTreeList, folderPaths, findFolder, openFolder, openModelDetail, getFullPath } =
  useModelExplorer()
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

const sortOrder = ref('name')

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

    // Starred entries always lead their group; the chosen sort order decides
    // within equal star state (Array#sort is stable).
    const starFirst = (a: ModelTreeNode, b: ModelTreeNode) =>
      Number(isFolderStarred(genModelKey(b))) - Number(isFolderStarred(genModelKey(a)))

    folderItems.sort((a, b) => {
      return starFirst(a, b) || a.basename.localeCompare(b.basename)
    })
    modelItems.sort((a, b) => {
      const byStar = starFirst(a, b)
      if (byStar) return byStar
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
