<template>
  <ResponseScroll class="h-full">
    <div class="px-8">
      <ModelContent
        v-model:editable="editable"
        :model="modelContent"
        @submit="handleSave"
        @reset="handleCancel"
      >
        <template #action="{ metadata }">
          <template v-if="editable">
            <Button variant="secondary" type="reset">{{ $t('cancel') }}</Button>
            <Button type="submit">{{ $t('save') }}</Button>
          </template>
          <template v-else>
            <Button
              v-show="metadata.modelPage"
              variant="ghost"
              size="icon-sm"
              @click="openModelPage(metadata.modelPage)"
            >
              <Eye class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              @click.stop="addModelNode(model)"
            >
              <Plus class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              @click.stop="copyModelNode(model)"
            >
              <Copy class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              @click.stop="loadPreviewWorkflow(model)"
            >
              <Workflow class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              @click="editable = true"
            >
              <PenSquare class="size-4" />
            </Button>
            <Button
              variant="destructive"
              size="icon-sm"
              @click="handleDelete"
            >
              <Trash2 class="size-4" />
            </Button>
          </template>
        </template>
      </ModelContent>
    </div>
  </ResponseScroll>
</template>

<script setup lang="ts">
import { Copy, Eye, PenSquare, Plus, Trash2, Workflow } from '@lucide/vue'
import ModelContent from 'components/ModelContent.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { genModelUrl, useModelNodeAction, useModels } from 'hooks/model'
import { useRequest } from 'hooks/request'
import { BaseModel, Model, WithResolved } from 'types/typings'
import { computed, ref } from 'vue'

interface Props {
  model: Model
}
const props = defineProps<Props>()

const { remove, update } = useModels()

const editable = ref(false)

const modelDetailUrl = genModelUrl(props.model)
const { data: extraInfo } = useRequest(modelDetailUrl, {
  method: 'GET',
})

const modelContent = computed(() => {
  return Object.assign({}, props.model, extraInfo.value)
})

const handleCancel = () => {
  editable.value = false
}

const handleSave = async (data: WithResolved<BaseModel>) => {
  await update(modelContent.value, data)
  editable.value = false
}

const handleDelete = async () => {
  await remove(props.model)
}

const openModelPage = (url: string) => {
  window.open(url, '_blank')
}

const { addModelNode, copyModelNode, loadPreviewWorkflow } =
  useModelNodeAction()
</script>
