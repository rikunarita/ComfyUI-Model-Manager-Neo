<script setup lang="ts">
import { GitCompareArrows, Plus, Star, Trash2, Upload } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import DialogHfUpload from 'components/DialogHfUpload.vue'
import SelectionBarZipnnButton from 'components/SelectionBarZipnnButton.vue'
import { Button } from 'components/ui/button'
import { useDialog } from 'hooks/dialog'
import { type ModelTreeNode } from 'hooks/explorer'
import { useFolderSelection } from 'hooks/folderSelection'
import { genModelFullName } from 'hooks/model'
import { useToast } from 'hooks/toast'
import { cn } from 'utils/cn'

interface Props {
  tree: ModelTreeNode[]
  /**
   * Folder-only extras (ZipNN batch button, folder star toggle). The folder
   * view offers them; the flat view's selection is model-only and its bar
   * never showed them.
   */
  folderActions?: boolean
  /** Outer horizontal margin; matches each layout's grid padding. */
  marginClass?: string
}
const props = withDefaults(defineProps<Props>(), { folderActions: true, marginClass: 'mx-4' })

const { t } = useI18n()
const { toast } = useToast()
const dialog = useDialog()

const {
  selection,
  selectionCount,
  addSelectedToWorkflow,
  deleteSelected,
  collectFolderModels,
  selectedFolderNodes,
  zipnnRunning,
  batchInverted,
  batchLabel,
  requestBatch,
  deltaPair,
  openDeltaDialog,
  allSelectedFoldersStarred,
  starSelectedFolders,
} = useFolderSelection(() => props.tree)

/** Folder batch upload: every model inside the selected folders, in one task. */
const uploadFoldersToHf = () => {
  const files = selectedFolderNodes.value
    .flatMap(folder => collectFolderModels(folder))
    .map(m => ({
      type: m.type,
      pathIndex: m.pathIndex,
      fullname: genModelFullName(m),
      sizeBytes: m.sizeBytes,
    }))
  if (files.length === 0) {
    toast.add({ severity: 'warn', summary: t('hfUpload.noFilesInFolders'), life: 6000 })
    return
  }
  dialog.open({
    key: 'model-manager-hf-upload',
    title: t('uploadToHuggingFace'),
    content: DialogHfUpload,
    contentProps: { files },
  })
}
</script>

<template>
  <!--
    Bulk actions of the selection mode (folder view): add to workflow,
    delete, ZipNN batch / delta, star and clear. All state and logic live in
    `useFolderSelection`; this is the template only.
  -->
  <div
    :class="
      cn(
        'mm-glass-light mm-scope mb-2 flex items-center justify-between gap-4 rounded-mm-ctl border border-mm-border px-4 py-2',
        props.marginClass,
      )
    "
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
      <Button
        v-if="folderActions && selectedFolderNodes.length > 0"
        variant="secondary"
        size="sm"
        @click="uploadFoldersToHf"
      >
        <Upload class="size-4" />
        {{ $t('uploadToHuggingFace') }}
      </Button>
      <SelectionBarZipnnButton
        :visible="folderActions && selectedFolderNodes.length > 0"
        :running="zipnnRunning"
        :inverted="batchInverted"
        :label="batchLabel"
        @request="requestBatch"
      />
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
        v-if="folderActions"
        variant="ghost"
        size="icon"
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
</template>
