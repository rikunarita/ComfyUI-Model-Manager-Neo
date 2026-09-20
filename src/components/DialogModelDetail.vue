<template>
  <ResponseScroll class="h-full">
    <div class="px-8">
      <ModelContent
        ref="contentRef"
        v-model:editable="editable"
        :model="modelContent"
        @submit="handleSave"
        @reset="handleCancel"
      >
        <template #action>
          <template v-if="editable">
            <!--
              type="button" + handler: cancelling with unsaved edits must ask
              first; a plain `type="reset"` discarded them unconditionally.
            -->
            <Button variant="secondary" type="button" @click="handleCancelClick">
              {{ $t('cancel') }}
            </Button>
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
            <div v-if="zipnnRunning" class="mr-auto flex h-[2.7rem] w-40 items-center gap-2">
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
                  class="mm-zipnn-button mr-auto size-[2.7rem] shrink-0"
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
              class="size-[2.7rem]"
              :title="starred ? $t('unstar') : $t('star')"
              :aria-label="starred ? $t('unstar') : $t('star')"
              :aria-pressed="starred"
              @click="toggleStar"
            >
              <Star
                class="size-5"
                :class="starred ? 'fill-current text-mm-warning' : 'text-mm-fg'"
              />
            </Button>
            <Button
              v-show="model.modelPage"
              variant="ghost"
              class="size-[2.7rem]"
              :class="platformLogo(model.modelPlatform) && 'text-white'"
              :style="platformBackgroundStyle(model.modelPlatform)"
              :title="$t('openModelPage')"
              :aria-label="$t('openModelPage')"
              @click="openModelPage(model.modelPage)"
            >
              <ExternalLink class="size-5" />
            </Button>
            <!--
              IDENTIFY BY HASH: asks the Civitai catalog which model version
              this very file is (by-hash reverse lookup; the sidecar hashes
              are tried before the file is read at all). A hit opens the
              resolved version; a miss says so in a toast.
            -->
            <Button
              variant="ghost"
              class="size-[2.7rem]"
              :title="$t('identifyByHashHint')"
              :aria-label="$t('identifyByHash')"
              :disabled="identifying"
              @click="identifyByHash"
            >
              <Loader2 v-if="identifying" class="size-5 animate-spin" />
              <HashReverseIcon v-else />
            </Button>
            <Button
              variant="ghost"
              class="size-[2.7rem]"
              :title="$t('addNode')"
              :aria-label="$t('addNode')"
              @click.stop="addModelNode(model)"
            >
              <Plus class="size-5" />
            </Button>
            <Button
              variant="ghost"
              class="size-[2.7rem]"
              :title="$t('copyNode')"
              :aria-label="$t('copyNode')"
              @click.stop="copyModelNode(model)"
            >
              <Copy class="size-5" />
            </Button>
            <Button
              v-show="hasPreview"
              variant="ghost"
              class="size-[2.7rem]"
              :title="$t('loadWorkflow')"
              :aria-label="$t('loadWorkflow')"
              @click.stop="loadPreviewWorkflow(model)"
            >
              <Workflow class="size-5" />
            </Button>
            <!--
              DOWNLOAD TO LOCAL: streams the stored file to the browser as an
              attachment (backend route serves it verbatim with a
              Content-Disposition filename of the model name as-is).
            -->
            <Button
              variant="ghost"
              class="size-[2.7rem]"
              :title="$t('downloadToLocal')"
              :aria-label="$t('downloadToLocal')"
              @click="downloadToLocal"
            >
              <Download class="size-5" />
            </Button>
            <Button
              variant="ghost"
              class="size-[2.7rem]"
              :title="$t('editModel')"
              :aria-label="$t('editModel')"
              @click="editable = true"
            >
              <PenSquare class="size-5" />
            </Button>
            <Button
              variant="destructive"
              class="size-[2.7rem]"
              :title="$t('deleteModel')"
              :aria-label="$t('deleteModel')"
              @click="handleDelete"
            >
              <Trash2 class="size-5" />
            </Button>
          </template>
        </template>
      </ModelContent>
    </div>
  </ResponseScroll>
</template>

<script setup lang="ts">
import {
  Copy,
  Download,
  ExternalLink,
  Loader2,
  PenSquare,
  Plus,
  Star,
  Trash2,
  Workflow,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import DialogIdentifyHash from 'components/DialogIdentifyHash.vue'
import HashReverseIcon from 'components/HashReverseIcon.vue'
import ModelContent from 'components/ModelContent.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Progress } from 'components/ui/progress'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { useDialog } from 'hooks/dialog'
import {
  genModelFullName,
  genModelUrl,
  normalizePreviews,
  useModelNodeAction,
  useModels,
} from 'hooks/model'
import { request, useRequest } from 'hooks/request'
import { isModelStarred, toggleModelStar } from 'hooks/stars'
import { useToast } from 'hooks/toast'
import {
  confirmSingleZipnn,
  startZipnnDeltaDecompress,
  zipnnRunningFor,
  zipnnState,
} from 'hooks/zipnn'
import { type BaseModel, type Model, type WithResolved } from 'types/typings'
import { assetUrl, platformBackgroundStyle, platformLogo } from 'utils/media'
import { genModelKey } from 'utils/model'

interface Props {
  model: Model
}
const props = defineProps<Props>()

const { t } = useI18n()
const { toast, confirm } = useToast()
const dialog = useDialog()
const { remove, update, data: modelsData } = useModels()

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

const contentRef = ref<InstanceType<typeof ModelContent> | null>(null)

/** Cancel with unsaved edits: confirm before throwing them away. */
const handleCancelClick = () => {
  const content = contentRef.value
  if (content?.isDirty()) {
    confirm.require({
      message: t('discardChangesConfirm'),
      header: t('discardChanges'),
      icon: 'pi pi-info-circle',
      rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
      acceptProps: { label: t('discardChanges'), severity: 'destructive' },
      accept: () => content.resetForm(),
      reject: () => {},
    })
    return
  }
  content?.resetForm()
}

/**
 * One-shot flag: after a save, the grid refresh replaces the listing object
 * while this window's props still point at the pre-save instance (the dialog
 * stack keeps the model it was opened with). The watcher below then swaps the
 * window's payload to the persisted instance exactly once - background
 * revalidations at any other moment must never reset an open editor.
 */
const pendingReflect = ref(false)

watch(
  () => modelsData.value[props.model.type],
  list => {
    if (!pendingReflect.value) return
    const key = genModelKey(props.model)
    const fresh = (list ?? []).find(m => genModelKey(m) === key)
    if (!fresh) return
    pendingReflect.value = false
    const item = dialog.stack.value.find(candidate => candidate.key === key)
    if (item) item.contentProps = { ...item.contentProps, model: fresh }
  },
)

const handleSave = async (data: WithResolved<BaseModel>) => {
  pendingReflect.value = true
  // updateModel already reports failures with a toast; a failed save simply
  // cancels the one-shot reflect so the editor keeps its state.
  await update(modelContent.value, data).catch(() => {
    pendingReflect.value = false
  })
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

/** Save the stored file into the browser's download folder under exactly the
 *  name it carries in the library (backend serves it as an attachment). */
const downloadToLocal = () => {
  const fullname = genModelFullName(props.model)
  const path = fullname.split('/').map(encodeURIComponent).join('/')
  const url = `/model-manager/model-file/${props.model.type}/${props.model.pathIndex ?? 0}/${path}`
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.model.basename}${props.model.extension}`
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/* ---- identify by hash ----------------------------------------------------- */
const identifying = ref(false)
const identifyByHash = async () => {
  identifying.value = true
  try {
    const params = new URLSearchParams({
      type: props.model.type,
      index: String(props.model.pathIndex ?? 0),
      filename: genModelFullName(props.model),
    })
    const result = await request(`/identify-by-hash?${params.toString()}`)
    if (result?.matched) {
      dialog.open({
        key: 'identify-hash',
        title: t('identifyByHash'),
        content: DialogIdentifyHash,
        contentProps: { result },
        defaultSize: { width: 560, height: 640 },
      })
    } else {
      toast.add({
        severity: 'info',
        summary: t('identifyByHash'),
        detail: t('identifyMiss'),
        life: 8000,
      })
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: t('identifyByHash'),
      detail: (error as Error).message,
      life: 8000,
    })
  } finally {
    identifying.value = false
  }
}

const { addModelNode, copyModelNode, loadPreviewWorkflow } = useModelNodeAction()

/** The workflow action needs a real preview (the NO-PREVIEW artwork is not one). */
const hasPreview = computed(() => normalizePreviews(props.model.preview).length > 0)

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
  confirmSingleZipnn(props.model, modelKey.value)
}
</script>
