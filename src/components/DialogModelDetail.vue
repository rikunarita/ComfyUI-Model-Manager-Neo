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
              button is replaced by its progress bar. The bar is a FIXED,
              compact width (and shrinkable, not `flex-1`): stretching it
              across the whole gap pushed the row past the column's width and
              its left end was clipped by the preview's `overflow-hidden`.
            -->
            <div v-if="zipnnRunning" class="mr-auto flex h-10 w-40 items-center gap-2">
              <Progress
                class="min-w-0 flex-1"
                :model-value="zipnnState.progress"
                :mode="zipnnState.progress > 0 ? 'determinate' : 'indeterminate'"
              />
              <span class="w-10 text-right text-xs text-mm-muted-fg tabular-nums">
                {{ zipnnState.progress }}%
              </span>
            </div>
            <Tooltip v-else-if="isSafetensorsModel || isDeltaModel" :delay-duration="300">
              <TooltipTrigger as-child>
                <!--
                  The shipped ZipNN artwork *is* the button (it already draws its
                  own glass plate and switches to a dark variant through the
                  media query embedded in the SVG), so it is rendered bare - no
                  Button chrome, no text label. Meaning is carried by the
                  tooltip + aria-label, and a compressed model inverts it.
                  Delta files (`.znn` inside a `*_DeltaZNN` folder) restore
                  through their base model with the same inverted artwork.
                -->
                <button
                  type="button"
                  class="mm-zipnn-button mr-auto size-12 shrink-0"
                  :aria-label="zipnnActionLabel"
                  :title="zipnnActionLabel"
                  @click="requestZipnn"
                >
                  <img
                    :src="zipnnIcon"
                    alt=""
                    class="size-full rounded-mm-ctl"
                    :class="(isCompressed || isDeltaModel) && 'hue-rotate-180 invert'"
                  />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" class="max-w-sm">
                {{ zipnnHint }}
              </TooltipContent>
            </Tooltip>
            <Button
              variant="ghost"
              size="icon-action"
              :title="starred ? $t('unstar') : $t('star')"
              :aria-label="starred ? $t('unstar') : $t('star')"
              :aria-pressed="starred"
              @click="toggleStar"
            >
              <Star
                class="size-6"
                :class="starred ? 'fill-current text-mm-warning' : 'text-mm-fg'"
              />
            </Button>
            <Button
              v-show="model.modelPage"
              variant="ghost"
              size="icon-action"
              :class="platformLogo(model.modelPlatform) && 'text-white'"
              :style="platformBackgroundStyle(model.modelPlatform)"
              :title="$t('openModelPage')"
              :aria-label="$t('openModelPage')"
              @click="openModelPage(model.modelPage)"
            >
              <ExternalLink class="size-6" />
            </Button>
            <Button
              variant="ghost"
              size="icon-action"
              :title="$t('addNode')"
              :aria-label="$t('addNode')"
              @click.stop="addModelNode(model)"
            >
              <Plus class="size-6" />
            </Button>
            <Button
              variant="ghost"
              size="icon-action"
              :title="$t('copyNode')"
              :aria-label="$t('copyNode')"
              @click.stop="copyModelNode(model)"
            >
              <Copy class="size-6" />
            </Button>
            <Button
              variant="ghost"
              size="icon-action"
              :title="$t('loadWorkflow')"
              :aria-label="$t('loadWorkflow')"
              @click.stop="loadPreviewWorkflow(model)"
            >
              <Workflow class="size-6" />
            </Button>
            <Button
              variant="ghost"
              size="icon-action"
              :title="$t('editModel')"
              :aria-label="$t('editModel')"
              @click="editable = true"
            >
              <PenSquare class="size-6" />
            </Button>
            <Button
              variant="destructive"
              size="icon-action"
              :title="$t('deleteModel')"
              :aria-label="$t('deleteModel')"
              @click="handleDelete"
            >
              <Trash2 class="size-6" />
            </Button>
          </template>
        </template>
      </ModelContent>
    </div>
  </ResponseScroll>
</template>

<script setup lang="ts">
import { Copy, ExternalLink, PenSquare, Plus, Star, Trash2, Workflow } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ModelContent from 'components/ModelContent.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Progress } from 'components/ui/progress'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { genModelFullName, genModelUrl, useModelNodeAction, useModels } from 'hooks/model'
import { useRequest } from 'hooks/request'
import { isModelStarred, toggleModelStar } from 'hooks/stars'
import { useToast } from 'hooks/toast'
import { startZipnn, startZipnnDeltaDecompress, zipnnRunningFor, zipnnState } from 'hooks/zipnn'
import { type BaseModel, type Model, type WithResolved } from 'types/typings'
import { assetUrl, platformBackgroundStyle, platformLogo } from 'utils/media'
import { genModelKey } from 'utils/model'

interface Props {
  model: Model
}
const props = defineProps<Props>()

const { t } = useI18n()
const { toast, confirm } = useToast()
const { remove, update } = useModels()

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
/** Delta files (`<ft>_delta_<base>.znn`) restore through their base model. */
const isDeltaModel = computed(() => props.model.extension === '.znn')
const modelKey = computed(() => genModelKey(props.model))
const zipnnRunning = computed(() => zipnnRunningFor(modelKey.value))

const zipnnActionLabel = computed(() =>
  isDeltaModel.value
    ? t('zipnnDeltaDecompress')
    : isCompressed.value
      ? t('zipnnDecompress')
      : t('zipnnCompress'),
)
const zipnnHint = computed(() =>
  isDeltaModel.value
    ? t('zipnnDeltaDecompressHint')
    : isCompressed.value
      ? t('zipnnDecompressHint')
      : t('zipnnCompressHint'),
)

/* ---- star ------------------------------------------------------------- */
const starred = computed(() => isModelStarred(modelKey.value))
const toggleStar = () => {
  toggleModelStar(modelKey.value)
}

// NOTE: the post-task grid refresh and the swap of this card to the renamed
// file live in App.vue (app lifetime), NOT here - a watcher inside this
// component only ran while the card was open, and a multi-gigabyte
// compression usually outlives the dialog.

const requestZipnn = () => {
  if (isDeltaModel.value) {
    confirm.require({
      message: t('zipnnDeltaConfirmDecompress', {
        name: `${props.model.basename}${props.model.extension}`,
      }),
      header: t('zipnnDeltaDecompress'),
      icon: 'pi pi-info-circle',
      rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
      acceptProps: { label: t('zipnnDeltaDecompress') },
      accept: () => {
        void startZipnnDeltaDecompress(
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
    return
  }
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
