<script setup lang="ts">
import { Check, ChevronDown, ChevronUp, ListChecks, Save, Trash2, X } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import DialogSaveCollection from 'components/DialogSaveCollection.vue'
import ResponseBreadcrumb from 'components/ResponseBreadcrumb.vue'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from 'components/ui/dropdown-menu'
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
const collectionMenuOpen = ref(false)

const collectionOptions = computed<SelectOptions[]>(() => {
  const saved = collectionState.collections.map(c => ({
    label: c.name,
    value: c.id,
    command: () => {
      collectionState.activeId = c.id
    },
  }))
  if (saved.length === 0) {
    // A blank menu reads as "nothing happens"; say what to do instead.
    return [
      {
        label: t('collectionsEmpty'),
        value: '__empty__',
        command: () => {},
      },
    ]
  }
  return saved
})

const openSaveCollection = () => {
  // The floppy lives inside the menu trigger; the save dialog must not open
  // with the collection menu still floating above the toolbar.
  collectionMenuOpen.value = false
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
        size="icon"
        class="shrink-0"
        :disabled="!canGoUp"
        @click="emits('up')"
      >
        <ChevronUp class="size-4" />
      </Button>
      <!--
        PATH READ-OUT GROWS ON DEMAND: the breadcrumb used to reserve a fixed
        `w-56` slot even at the folder root, i.e. permanent dead space in the
        bar. It now renders only while a path exists and takes exactly the
        width its crumbs need (capped at half the bar, internals ellipsise),
        so the space opens up only when the path actually gets deeper.
      -->
      <ResponseBreadcrumb
        v-if="breadcrumbItems.length"
        class="h-9 max-w-[50%] shrink-0"
        :items="breadcrumbItems"
      ></ResponseBreadcrumb>
    </template>

    <div class="min-w-40 flex-1">
      <ResponseInput
        v-model="search"
        :placeholder="$t('searchModels')"
        :allow-clear="true"
        suffix-icon="pi pi-search"
      ></ResponseInput>
    </div>

    <!--
      SAVE + COLLECTION AS ONE CONTROL: the floppy (save the current search)
      sits *inside* the collection button, a whisper of margin before the
      label, so the two former neighbours read as a single pill:
      [💾 Collection ▾]. The floppy keeps its own click / keyboard target -
      it opens the save dialog and `stop` keeps the menu shut - while every
      other pixel of the pill opens the menu that applies / switches saved
      searches. The floppy draws at FULL opacity (only the chevron stays
      dimmed) and plates on hover / focus, so the save zone keeps a visible
      boundary against the label instead of reading as its prefix glyph.
    -->
    <DropdownMenu v-model:open="collectionMenuOpen">
      <DropdownMenuTrigger as-child>
        <Button
          variant="secondary"
          class="shrink-0 whitespace-nowrap"
          :title="activeCol?.name ?? $t('collections')"
        >
          <span
            role="button"
            tabindex="0"
            class="-ml-1 grid size-6 shrink-0 place-items-center rounded-mm-ctl hover:bg-mm-fg/10 focus-visible:bg-mm-fg/10"
            :title="$t('collectionsSave')"
            :aria-label="$t('collectionsSave')"
            @click.stop="openSaveCollection"
            @keydown.enter.stop.prevent="openSaveCollection"
            @keydown.space.stop.prevent="openSaveCollection"
          >
            <Save class="size-4" />
          </span>
          <span class="ml-1 max-w-40 truncate">{{ activeCol?.name ?? $t('collections') }}</span>
          <ChevronDown class="size-4 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" class="max-h-75 min-w-32 overflow-y-auto">
        <DropdownMenuItem
          v-for="item in collectionOptions"
          :key="item.value"
          class="justify-between"
          @select="item.command?.()"
        >
          <span>{{ item.label }}</span>
          <Check v-if="collectionState.activeId === item.value" class="size-4 text-mm-accent" />
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    <Button
      v-if="activeCol"
      variant="ghost"
      size="icon"
      class="shrink-0"
      :title="$t('clearSelection')"
      :aria-label="$t('clearSelection')"
      @click="collectionState.activeId = null"
    >
      <X class="size-4" />
    </Button>
    <Button
      v-if="activeCol"
      variant="ghost"
      size="icon"
      class="shrink-0"
      :title="$t('delete')"
      :aria-label="$t('delete')"
      @click="removeCollection(activeCol.id)"
    >
      <Trash2 class="size-4" />
    </Button>

    <!--
      CONTENT-FIT SELECTS: the drop selects shrink-wrap their current label
      (ResponseSelect truncates inside a `max-w-*` ceiling) instead of
      reserving fixed frames that left a wide dead margin beside short
      labels; long values ellipsise at the ceiling rather than stretching
      the bar.
    -->
    <ResponseSelect
      v-if="mode === 'flat'"
      v-model="currentType"
      class="max-w-56 shrink-0"
      :items="typeOptions"
    ></ResponseSelect>
    <ResponseSelect
      v-model="sortOrder"
      class="max-w-56 shrink-0"
      :items="sortOrderOptions"
    ></ResponseSelect>
    <ResponseSelect
      v-model="cardSizeFlag"
      class="max-w-56 shrink-0"
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
