<template>
  <ResponseScroll class="h-full">
    <div class="px-8">
      <ModelContent
        v-model:editable="editable"
        :model="modelContent"
        @submit="handleSave"
        @reset="handleCancel"
      >
        <template #action>
          <template v-if="editable">
            <Button variant="secondary" type="reset">{{ $t('cancel') }}</Button>
            <Button type="submit">{{ $t('save') }}</Button>
          </template>
          <template v-else>
            <!--
              ZipNN lives in the empty left half of this row (the gap between
              the preview and the table). While a task for THIS model runs the
              button is replaced by its progress bar.
            -->
            <div v-if="zipnnRunning" class="mr-auto flex h-10 min-w-40 flex-1 items-center gap-2">
              <Progress
                class="flex-1"
                :model-value="zipnnState.progress"
                :mode="zipnnState.progress > 0 ? 'determinate' : 'indeterminate'"
              />
              <span class="w-10 text-right text-xs text-mm-muted-fg tabular-nums">
                {{ zipnnState.progress }}%
              </span>
            </div>
            <Tooltip v-else-if="isSafetensorsModel" :delay-duration="300">
              <TooltipTrigger as-child>
                <Button
                  variant="secondary"
                  class="mm-zipnn-button mr-auto h-10 gap-2 px-4"
                  :aria-label="isCompressed ? $t('zipnnDecompress') : $t('zipnnCompress')"
                  @click="requestZipnn"
                >
                  <img
                    :src="zipnnIcon"
                    alt=""
                    class="size-6"
                    :class="isCompressed && 'hue-rotate-180 invert'"
                  />
                  <span class="text-sm font-medium">
                    {{ isCompressed ? $t('zipnnDecompress') : $t('zipnnCompress') }}
                  </span>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" class="max-w-sm">
                {{ isCompressed ? $t('zipnnDecompressHint') : $t('zipnnCompressHint') }}
              </TooltipContent>
            </Tooltip>
            <Button
              v-show="model.modelPage"
              variant="ghost"
              size="icon-sm"
              :title="$t('openModelPage')"
              :aria-label="$t('openModelPage')"
              @click="openModelPage(model.modelPage)"
            >
              <ExternalLink class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              :title="$t('addNode')"
              :aria-label="$t('addNode')"
              @click.stop="addModelNode(model)"
            >
              <Plus class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              :title="$t('copyNode')"
              :aria-label="$t('copyNode')"
              @click.stop="copyModelNode(model)"
            >
              <Copy class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              :title="$t('loadWorkflow')"
              :aria-label="$t('loadWorkflow')"
              @click.stop="loadPreviewWorkflow(model)"
            >
              <Workflow class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              :title="$t('editModel')"
              :aria-label="$t('editModel')"
              @click="editable = true"
            >
              <PenSquare class="size-4" />
            </Button>
            <Button
              variant="destructive"
              size="icon-sm"
              :title="$t('deleteModel')"
              :aria-label="$t('deleteModel')"
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
import { Copy, ExternalLink, PenSquare, Plus, Trash2, Workflow } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ModelContent from 'components/ModelContent.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Progress } from 'components/ui/progress'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { genModelFullName, genModelUrl, useModelNodeAction, useModels } from 'hooks/model'
import { useRequest } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { startZipnn, zipnnRunningFor, zipnnState } from 'hooks/zipnn'
import { type BaseModel, type Model, type WithResolved } from 'types/typings'
import { assetUrl } from 'utils/media'
import { genModelKey } from 'utils/model'

interface Props {
  model: Model
}
const props = defineProps<Props>()

const { t } = useI18n()
const { toast, confirm } = useToast()
const { remove, update, refreshFolder } = useModels()

const editable = ref(false)

const modelDetailUrl = genModelUrl(props.model)
const { data: extraInfo } = useRequest(modelDetailUrl, {
  method: 'GET',
  onError: error => {
    toast.add({
      severity: 'error',
      summary: t('modelInfoFailed', { message: error.message }),
      life: 8000,
    })
  },
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

const openModelPage = (url?: string) => {
  if (!url) {
    toast.add({ severity: 'info', summary: t('noModelPage'), life: 4000 })
    return
  }
  window.open(url, '_blank')
}

const { addModelNode, copyModelNode, loadPreviewWorkflow } = useModelNodeAction()

/* ---- ZipNN ---------------------------------------------------------- */
const zipnnIcon = assetUrl('zipnn-button')
const isSafetensorsModel = computed(() => props.model.extension === '.safetensors')
const isCompressed = computed(() => props.model.basename.endsWith('.znn'))
const modelKey = computed(() => genModelKey(props.model))
const zipnnRunning = computed(() => zipnnRunningFor(modelKey.value))

// Refresh the grid once a ZipNN task for THIS model settles, so the card
// switches between `.safetensors` and `.znn.safetensors` without a manual
// refresh.
watch(
  () => zipnnState.active,
  (active, wasActive) => {
    if (!active && wasActive && zipnnState.lastTargetKey === modelKey.value) {
      void refreshFolder(props.model.type)
    }
  },
)

const requestZipnn = () => {
  const compressing = !isCompressed.value
  confirm.require({
    // deliberately NOT a Danger confirmation: compression is reversible and
    // never deletes user data without writing the counterpart first.
    message: compressing ? t('zipnnConfirmCompress') : t('zipnnConfirmDecompress'),
    header: compressing ? t('zipnnCompress') : t('zipnnDecompress'),
    icon: 'pi pi-info-circle',
    rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
    acceptProps: { label: compressing ? t('zipnnCompress') : t('zipnnDecompress') },
    accept: () => {
      void startZipnn(
        compressing ? 'compress' : 'decompress',
        {
          type: props.model.type,
          pathIndex: props.model.pathIndex,
          fullname: genModelFullName(props.model),
        },
        modelKey.value,
      )
    },
    reject: () => {},
  })
}
</script>
