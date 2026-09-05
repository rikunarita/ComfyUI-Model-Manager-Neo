<template>
  <form
    ref="container"
    @submit.prevent="handleSubmit"
    @reset.prevent="handleReset"
  >
    <div class="mx-auto w-full max-w-[50rem]">
      <div
        :class="[
          'relative flex gap-4 overflow-hidden',
          $xl('flex-row', 'flex-col'),
        ]"
      >
        <ModelPreview
          class="shrink-0"
          v-model:editable="editable"
        ></ModelPreview>

        <div class="flex flex-col gap-4 overflow-hidden">
          <div class="flex h-10 items-center justify-end gap-4">
            <slot name="action" :metadata="formInstance.metadata.value"></slot>
          </div>

          <ModelBaseInfo v-model:editable="editable"></ModelBaseInfo>
        </div>
      </div>

      <Tabs default-value="0" class="mt-4">
        <TabsList class="grid w-full grid-cols-2">
          <TabsTrigger value="0">Description</TabsTrigger>
          <TabsTrigger value="1">Metadata</TabsTrigger>
        </TabsList>
        <div class="py-4">
          <TabsContent value="0">
            <ModelDescription v-model:editable="editable"></ModelDescription>
          </TabsContent>
          <TabsContent value="1">
            <ModelMetadata></ModelMetadata>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  </form>
</template>

<script setup lang="ts">
import ModelBaseInfo from 'components/ModelBaseInfo.vue'
import ModelDescription from 'components/ModelDescription.vue'
import ModelMetadata from 'components/ModelMetadata.vue'
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
import { cloneDeep } from 'es-toolkit'
import { BaseModel, WithResolved } from 'types/typings'
import { ref, toRaw, watch } from 'vue'

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
