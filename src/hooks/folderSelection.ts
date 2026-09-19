import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { type ModelTreeNode } from 'hooks/explorer'
import { genModelFullName, useModelNodeAction, useModels } from 'hooks/model'
import { applyFolderStars, isFolderStarred } from 'hooks/stars'
import { useToast } from 'hooks/toast'
import { queueZipnnBatches, useSelection, zipnnState } from 'hooks/zipnn'
import { useZipnnDeltaDialog } from 'hooks/zipnnDelta'
import { genModelKey, isBundleFolderName } from 'utils/model'

/**
 * Everything the selection bulk bar of the folder view needs: the selected
 * nodes resolved against the current tree, the bulk actions (add to
 * workflow / delete / star / clear) and the ZipNN batch & delta controls.
 * Lives in a composable so the bar is a dumb template.
 */
export const useFolderSelection = (getTree: () => ModelTreeNode[]) => {
  const { t } = useI18n()
  const { toast, confirm } = useToast()
  const selection = useSelection()
  const selectionCount = selection.count
  const { addModelNode } = useModelNodeAction()
  const { remove } = useModels()

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
      .map(key => findNodeByKey(getTree(), key))
      .filter((n): n is ModelTreeNode => Boolean(n))

  const collectFolderModels = (node: ModelTreeNode): ModelTreeNode[] => {
    const models: ModelTreeNode[] = []
    for (const child of node.children ?? []) {
      if (child.isFolder) models.push(...collectFolderModels(child))
      else models.push(child)
    }
    return models
  }

  /** Type-root nodes are the library's top level (`checkpoints`, `loras`, ...). */
  const isTypeRootNode = (n: ModelTreeNode) =>
    Boolean(n.type) && n.basename === n.type && !n.subFolder

  const selectedFolderNodes = computed(() => selectedNodes().filter(n => n.isFolder))
  const selectedModelNodes = computed(() => selectedNodes().filter(n => !n.isFolder))

  /**
   * BUG FIX: "Add to workflow" on a folder selection used to add NOTHING - the
   * old helper filtered folders out and only looked at the current view, so
   * the models inside a selected folder were never expanded into nodes.
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

  /* ---- ZipNN batch (folder selection) ---------------------------------- */
  const zipnnRunning = computed(
    () =>
      zipnnState.active &&
      selectedFolderNodes.value.some(n => genModelKey(n) === zipnnState.targetKey),
  )
  const batchInverted = computed(
    () =>
      selectedFolderNodes.value.length > 0 &&
      selectedFolderNodes.value.every(n => isBundleFolderName(n.basename)),
  )
  const batchModeFor = (n: ModelTreeNode): 'compress' | 'decompress' | 'auto' =>
    isBundleFolderName(n.basename) ? 'decompress' : isTypeRootNode(n) ? 'auto' : 'compress'

  const batchLabel = computed(() => {
    const folders = selectedFolderNodes.value
    if (folders.length === 0) return t('zipnnBatchCompress')
    if (folders.every(n => isBundleFolderName(n.basename))) return t('zipnnBatchDecompress')
    if (folders.some(n => batchModeFor(n) === 'auto')) return t('zipnnBatch')
    return t('zipnnBatchCompress')
  })

  const requestBatch = () => {
    const folders = selectedFolderNodes.value
    if (folders.length === 0) return
    const modes = folders.map(batchModeFor)
    const names = folders.map(f => f.basename).join(', ')
    const decompressing = modes.every(m => m === 'decompress')
    const hasAuto = modes.some(m => m === 'auto')
    const message = decompressing
      ? t('zipnnBatchConfirmDecompress', { name: names })
      : hasAuto
        ? t('zipnnBatchConfirmAuto', { name: names })
        : t('zipnnBatchConfirmCompress', { name: names })
    confirm.require({
      message,
      header: batchLabel.value,
      icon: 'pi pi-info-circle',
      rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
      acceptProps: { label: batchLabel.value },
      accept: () => {
        const items = folders
          .map(f => ({
            mode: batchModeFor(f),
            folder: {
              type: f.type,
              pathIndex: f.pathIndex,
              folder: isTypeRootNode(f) ? '.' : genModelFullName(f),
            },
            key: genModelKey(f),
          }))
          // never queue an unresolved target (defence in depth; the start guard
          // would reject it with a toast anyway)
          .filter(it => it.folder.folder && it.folder.type)
        if (items.length === 0) {
          toast.add({ severity: 'warn', summary: t('zipnnBatchInvalidTarget'), life: 8000 })
          return
        }
        queueZipnnBatches(items)
      },
      reject: () => {},
    })
  }

  /* ---- delta compression (exactly two plain models selected) ----------- */
  const { deltaPair, openDeltaDialog } = useZipnnDeltaDialog(selectedModelNodes)

  /* ---- star toggle for the selected folders ---------------------------- */
  const allSelectedFoldersStarred = computed(
    () =>
      selectedFolderNodes.value.length > 0 &&
      selectedFolderNodes.value.every(n => isFolderStarred(genModelKey(n))),
  )
  const starSelectedFolders = () => {
    applyFolderStars(selectedFolderNodes.value.map(n => genModelKey(n)))
  }

  return {
    selection,
    selectionCount,
    collectFolderModels,
    selectedFolderNodes,
    addSelectedToWorkflow,
    deleteSelected,
    zipnnRunning,
    batchInverted,
    batchLabel,
    requestBatch,
    deltaPair,
    openDeltaDialog,
    allSelectedFoldersStarred,
    starSelectedFolders,
  }
}
