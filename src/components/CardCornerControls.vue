<script setup lang="ts">
import { Star } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ZipnnProgressRing from 'components/ZipnnProgressRing.vue'
import { genModelFullName } from 'hooks/model'
import { isFolderStarred, isModelStarred, toggleFolderStar, toggleModelStar } from 'hooks/stars'
import { useToast } from 'hooks/toast'
import {
  confirmSingleZipnn,
  startZipnnBatch,
  startZipnnDeltaDecompress,
  zipnnRunningFor,
  zipnnState,
} from 'hooks/zipnn'
import { type BaseModel } from 'types/typings'
import { assetUrl } from 'utils/media'
import { genModelKey, isBundleFolderName } from 'utils/model'

interface Props {
  model: BaseModel
}
const props = defineProps<Props>()

const { t } = useI18n()
const { toast, confirm } = useToast()

/* ---- star badge ------------------------------------------------------ */
const modelKey = computed(() => genModelKey(props.model))
const starred = computed(() =>
  props.model.isFolder ? isFolderStarred(modelKey.value) : isModelStarred(modelKey.value),
)
const toggleStar = () => {
  if (props.model.isFolder) toggleFolderStar(modelKey.value)
  else toggleModelStar(modelKey.value)
}

/* ---- ZipNN corner button --------------------------------------------- */
const zipnnIcon = assetUrl('zipnn-button')
const isFolder = computed(() => Boolean(props.model.isFolder))
const folderName = computed(() => props.model.basename)
const isDeltaModel = computed(() => props.model.extension === '.znn')
const isCompressedModel = computed(() => props.model.basename.endsWith('.znn'))
/** Type-root folder cards (the library's top level) never batch-process. */
const isTypeRootFolder = computed(
  () => isFolder.value && !props.model.subFolder && props.model.basename === props.model.type,
)
const zipnnApplicable = computed(() => {
  // Every folder is a batch target: plain folders compress into a
  // `<name>_DeltaZNN` bundle, bundles (batch AND delta folders) decompress
  // back, type roots let the backend pick the direction (auto).
  if (isFolder.value) return true
  return isCompressedModel.value || props.model.extension === '.safetensors'
})
/** Direction of the folder batch: bundles decompress, type roots auto. */
const zipnnFolderMode = computed<'compress' | 'decompress' | 'auto'>(() => {
  if (isBundleFolderName(folderName.value)) return 'decompress'
  return isTypeRootFolder.value ? 'auto' : 'compress'
})
const zipnnInverted = computed(() => {
  if (isFolder.value) return isBundleFolderName(folderName.value)
  return isCompressedModel.value || isDeltaModel.value
})
const zipnnRunning = computed(() => zipnnRunningFor(modelKey.value))
/** 0-100, drives the circular progress ring on the corner button. */
const zipnnProgress = computed(() => zipnnState.progress)
const zipnnLabel = computed(() => {
  if (isFolder.value) {
    if (isBundleFolderName(folderName.value)) return t('zipnnBatchDecompress')
    return isTypeRootFolder.value ? t('zipnnBatch') : t('zipnnBatchCompress')
  }
  if (isDeltaModel.value) return t('zipnnDeltaDecompress')
  return isCompressedModel.value ? t('zipnnDecompress') : t('zipnnCompress')
})

const requestZipnn = () => {
  const model = props.model
  const key = modelKey.value
  if (isFolder.value) {
    const mode = zipnnFolderMode.value
    // type-root folders address themselves as '.' (their own base path)
    const folderRel = isTypeRootFolder.value ? '.' : genModelFullName(model)
    if (!model.type || !folderRel) {
      toast.add({ severity: 'warn', summary: t('zipnnBatchInvalidTarget'), life: 8000 })
      return
    }
    const message =
      mode === 'decompress'
        ? t('zipnnBatchConfirmDecompress', { name: folderName.value })
        : mode === 'auto'
          ? t('zipnnBatchConfirmAuto', { name: folderName.value })
          : t('zipnnBatchConfirmCompress', { name: folderName.value })
    confirm.require({
      message,
      header: zipnnLabel.value,
      icon: 'pi pi-info-circle',
      rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
      acceptProps: { label: zipnnLabel.value },
      accept: () => {
        void startZipnnBatch(
          mode,
          {
            type: model.type,
            pathIndex: model.pathIndex,
            folder: folderRel,
          },
          key,
        )
      },
      reject: () => {},
    })
    return
  }
  if (isDeltaModel.value) {
    confirm.require({
      message: t('zipnnDeltaConfirmDecompress', {
        name: `${model.basename}${model.extension}`,
      }),
      header: t('zipnnDeltaDecompress'),
      icon: 'pi pi-info-circle',
      rejectProps: { label: t('cancel'), severity: 'secondary', outlined: true },
      acceptProps: { label: t('zipnnDeltaDecompress') },
      accept: () => {
        void startZipnnDeltaDecompress(
          {
            type: model.type,
            pathIndex: model.pathIndex,
            fullname: genModelFullName(model),
          },
          key,
        )
      },
      reject: () => {},
    })
    return
  }
  confirmSingleZipnn(model, key)
}
</script>

<template>
  <!--
    Top-right control row on EVERY card: the star toggle plus the ZipNN
    corner button. The star is an outline glyph when unstarred and a filled
    yellow star when starred; clicking toggles it. The ZipNN button is the
    shipped SVG artwork (same confirmation, same inverted colours for
    compressed models / bundle folders as the detail call-to-action); while
    its task runs it shows a circular progress ring (batch & delta included)
    instead of a plain spinner.
  -->
  <div class="absolute top-2 right-2 z-20 flex items-start gap-1">
    <button
      type="button"
      class="mm-transition grid size-8 shrink-0 place-items-center rounded-full border backdrop-blur-md active:scale-90"
      :class="
        starred
          ? 'border-mm-warning/60 bg-mm-bg/70 text-mm-warning shadow-mm-glass-1'
          : 'border-mm-fg/25 bg-mm-bg/50 text-mm-fg/70 hover:border-mm-warning/60 hover:text-mm-warning'
      "
      :title="starred ? $t('unstar') : $t('star')"
      :aria-label="starred ? $t('unstar') : $t('star')"
      :aria-pressed="starred"
      @click.stop.prevent="toggleStar"
      @dblclick.stop.prevent
    >
      <Star class="size-4" :class="starred && 'fill-current'" :stroke-width="2" />
    </button>
    <button
      v-if="zipnnApplicable"
      type="button"
      class="mm-transition mm-zipnn-button size-8 shrink-0 rounded-mm-ctl"
      :title="zipnnLabel"
      :aria-label="zipnnLabel"
      :disabled="zipnnRunning"
      @click.stop.prevent="requestZipnn"
      @dblclick.stop.prevent
    >
      <ZipnnProgressRing v-if="zipnnRunning" :progress="zipnnProgress" />
      <img
        v-else
        :src="zipnnIcon"
        alt=""
        class="size-full rounded-mm-ctl"
        :class="zipnnInverted && 'hue-rotate-180 invert'"
      />
    </button>
  </div>
</template>
