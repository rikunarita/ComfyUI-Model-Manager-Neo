<template>
  <form ref="container" @submit.prevent="handleSubmit" @reset.prevent="handleReset">
    <!--
      LAYOUT FIX: the form used to cap itself at `max-w-200` and centre, so on
      wide download/detail dialogs the whole right half stayed empty while the
      controls squeezed into a narrow middle column. The content now fills the
      dialog and the info column stretches with it.
    -->
    <div class="w-full">
      <!--
        LAYOUT FIX (download dialog was "completely broken"): the editor row
        used to be a container-query flex box (`relative flex overflow-hidden`
        + `$xl(flex-row/flex-col)`) with the preview as a fixed-width flex
        child. Inside the create-task dialog - nested scrollers, a zero-width
        first measurement and a partially mounted sibling - that box could
        place the gallery anywhere while the metadata column collapsed. The
        `stacked` variant below is a plain single-column CSS grid: one column,
        no direction to flip, no shrink arithmetic, every block full-width and
        in source order. The detail window keeps the side-by-side `auto` row.
      -->
      <div
        :class="
          layout === 'stacked'
            ? 'grid grid-cols-1 gap-4'
            : ['relative flex gap-4 overflow-hidden', $xl('flex-row', 'flex-col')]
        "
      >
        <!--
          WIDTH FIX: the stacked (download dialog) column used to be
          `justify-self-center`, i.e. sized to its content - which let the old
          gallery strip's enormous min-content width inflate the column past
          the dialog edges. ModelPreview now owns its sizing: full-width and
          min-w-0 when stacked, content-sized and shrink-0 in the detail row.
        -->
        <ModelPreview v-model:editable="editable" :layout="layout"></ModelPreview>

        <div
          :class="
            layout === 'stacked'
              ? 'flex min-w-0 flex-col gap-4'
              : 'flex flex-1 flex-col gap-4 overflow-hidden'
          "
        >
          <div class="min-h-10 overflow-x-auto">
            <!--
              Inner row: `w-max min-w-full` + justify-end keeps the buttons
              right-aligned while they fit, and overflows to the RIGHT (the
              scrollable direction) when they don't - plain `justify-end` on
              the scroll container would overflow left, where scrolling
              cannot reach.
            -->
            <div class="flex w-max min-w-full items-center justify-end gap-4 *:shrink-0">
              <slot name="action" :metadata="formInstance.metadata.value"></slot>
            </div>
          </div>

          <ModelBaseInfo v-model:editable="editable"></ModelBaseInfo>
        </div>
      </div>

      <Tabs default-value="0" class="mt-4">
        <TabsList class="grid w-full grid-cols-2">
          <TabsTrigger value="0">{{ $t('description') }}</TabsTrigger>
          <TabsTrigger value="1">{{ $t('information') }}</TabsTrigger>
        </TabsList>
        <div class="py-4">
          <TabsContent value="0">
            <ModelDescription v-model:editable="editable"></ModelDescription>
          </TabsContent>
          <TabsContent value="1">
            <!-- Read-only by design: the parsed notes front-matter (and the
                 raw safetensors metadata) are a report, not an editor. -->
            <ModelInformation :editable="editable ?? false"></ModelInformation>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  </form>
</template>

<script setup lang="ts">
import { cloneDeep } from 'es-toolkit'
import { ref, toRaw, watch } from 'vue'
import ModelBaseInfo from 'components/ModelBaseInfo.vue'
import ModelDescription from 'components/ModelDescription.vue'
import ModelInformation from 'components/ModelInformation.vue'
import ModelPreview from 'components/ModelPreview.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { useContainerQueries } from 'hooks/container'
import {
  useModelBaseInfoEditor,
  useModelDescriptionEditor,
  useModelFormData,
  useModelMetadataEditor,
  useModelPreviewEditor,
} from 'hooks/model'
import { type BaseModel, type WithResolved } from 'types/typings'

interface Props {
  model: BaseModel
  /**
   * `auto`  – side-by-side gallery + metadata row (model detail window).
   * `stacked` – single-column grid, gallery on top (download task window):
   *            deterministic at any width, no container query involved.
   */
  layout?: 'auto' | 'stacked'
}

const props = defineProps<Props>()
const editable = defineModel<boolean>('editable')

const emits = defineEmits<{
  submit: [formData: WithResolved<BaseModel>]
  reset: []
}>()

const formInstance = useModelFormData(() => cloneDeep(toRaw(props.model)))

useModelBaseInfoEditor(formInstance)
const previewEditor = useModelPreviewEditor(formInstance)
useModelDescriptionEditor(formInstance)
useModelMetadataEditor(formInstance)

/** JSON baseline of the form, taken whenever the editor reaches a clean
 *  state (entering edit mode, reset, or a fresh model instance). */
const dirtySnapshot = ref('')
/** The whole editor state that a save would persist: form fields PLUS the
 *  gallery order and the currently selected primary page (the page pick
 *  lives outside formData until submit). */
const editorState = () =>
  JSON.stringify({
    form: toRaw(formInstance.formData.value),
    gallery: previewEditor.defaultContent.value,
    page: previewEditor.defaultContentPage.value,
  })
const takeSnapshot = () => {
  dirtySnapshot.value = editorState()
}
/** True while the editor holds unsaved edits (parents gate cancel on it). */
const isDirty = () => editorState() !== dirtySnapshot.value

watch(
  editable,
  v => {
    if (v) takeSnapshot()
  },
  { immediate: true },
)

const handleReset = () => {
  formInstance.reset()
  takeSnapshot()
  emits('reset')
}

/** External reset entry point (confirmed cancel, parent-driven refreshes). */
const resetForm = () => handleReset()

defineExpose({ isDirty, resetForm })

const handleSubmit = async () => {
  const data = formInstance.submit()
  emits('submit', data)
}

watch(
  () => props.model,
  () => {
    handleReset()
  },
)

const container = ref<HTMLElement | null>(null)
const { $xl } = useContainerQueries(container)
</script>
