<script setup lang="ts">
import { GitCompareArrows, Plus, Star, Trash2 } from '@lucide/vue'
import SelectionBarZipnnButton from 'components/SelectionBarZipnnButton.vue'
import { Button } from 'components/ui/button'
import { type ModelTreeNode } from 'hooks/explorer'
import { useFolderSelection } from 'hooks/folderSelection'
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

const {
  selection,
  selectionCount,
  addSelectedToWorkflow,
  deleteSelected,
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
</template>
