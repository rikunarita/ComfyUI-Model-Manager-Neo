<template>
  <form ref="container" @submit.prevent="handleSubmit" @reset.prevent="handleReset">
    <!--
      LAYOUT FIX: the form used to cap itself at `max-w-200` and centre, so on
      wide download/detail dialogs the whole right half stayed empty while the
      controls squeezed into a narrow middle column. The content now fills the
      dialog and the info column stretches with it.
    -->
    <div class="w-full">
      <div :class="['relative flex gap-4 overflow-hidden', $xl('flex-row', 'flex-col')]">
        <ModelPreview v-model:editable="editable" class="shrink-0"></ModelPreview>

        <div class="flex flex-1 flex-col gap-4 overflow-hidden">
          <div class="flex min-h-10 items-center justify-end gap-4">
            <slot name="action" :metadata="formInstance.metadata.value"></slot>
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
            <ModelInformation></ModelInformation>
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
}

const props = defineProps<Props>()
const editable = defineModel<boolean>('editable')

const emits = defineEmits<{
  submit: [formData: WithResolved<BaseModel>]
  reset: []
}>()

const formInstance = useModelFormData(() => cloneDeep(toRaw(props.model)))

useModelBaseInfoEditor(formInstance)
useModelPreviewEditor(formInstance)
useModelDescriptionEditor(formInstance)
useModelMetadataEditor(formInstance)

const handleReset = () => {
  formInstance.reset()
  emits('reset')
}

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
