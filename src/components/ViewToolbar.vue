<script setup lang="ts">
import { ChevronUp, ListChecks, Save, Trash2, X } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import DialogSaveCollection from 'components/DialogSaveCollection.vue'
import ResponseBreadcrumb from 'components/ResponseBreadcrumb.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import {
  activeCollection,
  collectionState,
  removeCollection,
  type SmartCollectionQuery,
} from 'hooks/collections'
import { useDialog } from 'hooks/dialog'
import { useGridSelectOptions } from 'hooks/gridOptions'
import { type BreadcrumbItem } from 'types/breadcrumb'
import { type SelectOptions } from 'types/typings'

/**
 * The shared second toolbar of both layouts: identical control set, only the
 * model-type select is flat-view-only and the folder view prefixes its
 * parent-navigation (up button + breadcrumb). The whole bar scrolls
 * horizontally instead of squeezing/hiding controls when the window is narrow.
 */
interface Props {
  mode: 'flat' | 'folder'
  breadcrumbItems?: BreadcrumbItem[]
  canGoUp?: boolean
  sortOrderOptions: SelectOptions[]
  typeOptions?: SelectOptions[]
  selectionEnabled?: boolean
  /** Snapshot of the current search state for "save current search". */
  getQuery: () => SmartCollectionQuery
}
const props = withDefaults(defineProps<Props>(), {
  breadcrumbItems: () => [],
  canGoUp: false,
  typeOptions: () => [],
  selectionEnabled: false,
})

const emits = defineEmits<{
  up: []
  'toggle-select': []
}>()

const search = defineModel<string | undefined>('search')
const sortOrder = defineModel<string>('sortOrder', { required: true })
const currentType = defineModel<string | undefined>('currentType')

const { t } = useI18n()
const dialog = useDialog()
const { cardSizeOptions, cardSizeFlag } = useGridSelectOptions()

const activeCol = computed(() => activeCollection())

const collectionOptions = computed<SelectOptions[]>(() => [
  ...collectionState.collections.map(c => ({
    label: c.name,
    value: c.id,
    command: () => {
      collectionState.activeId = c.id
    },
  })),
])

const openSaveCollection = () => {
  dialog.open({
    key: 'save-collection',
    title: t('collectionsSave'),
    content: DialogSaveCollection,
    contentProps: { query: props.getQuery() },
    defaultSize: { width: 420, height: 190 },
  })
}
</script>

<template>
  <!--
    `overflow-x-auto` + non-shrinking children: a narrow window scrolls the
    bar sideways instead of clipping controls out of sight (the defect the
    unified toolbar fixes).
  -->
  <div class="flex w-full items-center gap-4 overflow-x-auto px-4 pb-4">
    <template v-if="mode === 'folder'">
      <Button
        variant="ghost"
        size="icon-sm"
        class="shrink-0"
        :disabled="!canGoUp"
        @click="emits('up')"
      >
        <ChevronUp class="size-4" />
      </Button>
      <ResponseBreadcrumb class="h-10 w-56 shrink-0" :items="breadcrumbItems"></ResponseBreadcrumb>
    </template>

    <div class="min-w-40 flex-1">
      <ResponseInput
        v-model="search"
        :placeholder="$t('searchModels')"
        :allow-clear="true"
        suffix-icon="pi pi-search"
      ></ResponseInput>
    </div>

    <ResponseSelect
      v-model="collectionState.activeId"
      class="w-44 shrink-0"
      :items="collectionOptions"
    >
      <template #label>
        {{ activeCol?.name ?? $t('collections') }}
      </template>
    </ResponseSelect>
    <Button
      variant="secondary"
      size="icon"
      class="shrink-0"
      :title="$t('collectionsSave')"
      :aria-label="$t('collectionsSave')"
      @click="openSaveCollection"
    >
      <Save class="size-4" />
    </Button>
    <Button
      v-if="activeCol"
      variant="ghost"
      size="icon-sm"
      class="shrink-0"
      :title="$t('clearSelection')"
      :aria-label="$t('clearSelection')"
      @click="collectionState.activeId = null"
    >
      <X class="size-3.5" />
    </Button>
    <Button
      v-if="activeCol"
      variant="ghost"
      size="icon-sm"
      class="shrink-0"
      :title="$t('delete')"
      :aria-label="$t('delete')"
      @click="removeCollection(activeCol.id)"
    >
      <Trash2 class="size-3.5" />
    </Button>

    <ResponseSelect
      v-if="mode === 'flat'"
      v-model="currentType"
      class="w-36 shrink-0"
      :items="typeOptions"
    ></ResponseSelect>
    <ResponseSelect
      v-model="sortOrder"
      class="w-36 shrink-0"
      :items="sortOrderOptions"
    ></ResponseSelect>
    <ResponseSelect
      v-model="cardSizeFlag"
      class="w-36 shrink-0"
      :items="cardSizeOptions"
    ></ResponseSelect>

    <slot name="extra"></slot>

    <Button
      variant="secondary"
      size="icon"
      class="shrink-0"
      :class="selectionEnabled && 'border-mm-accent/50 bg-mm-accent/20 text-mm-accent'"
      :title="$t('selectFiles')"
      :aria-label="$t('selectFiles')"
      :aria-pressed="selectionEnabled"
      @click="emits('toggle-select')"
    >
      <ListChecks class="size-4" />
    </Button>
  </div>
</template>
