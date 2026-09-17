import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { useI18n } from 'vue-i18n'
import DialogZipnnDelta from 'components/DialogZipnnDelta.vue'
import { useDialog } from 'hooks/dialog'
import { type BaseModel } from 'types/typings'

/**
 * The "delta compress" pair picker of the selection bar. Both grids (flat and
 * folder view) offer it with identical semantics - exactly two plain
 * `.safetensors` models selected - so the pair detection and the dialog
 * opening live here once instead of twice.
 */
export const useZipnnDeltaDialog = (getModels: MaybeRefOrGetter<BaseModel[]>) => {
  const { t } = useI18n()
  const dialog = useDialog()

  const deltaPair = computed(() => {
    const models = toValue(getModels).filter(
      m => m.extension === '.safetensors' && !m.basename.endsWith('.znn'),
    )
    return models.length === 2 ? models : null
  })

  const openDeltaDialog = () => {
    const pair = deltaPair.value
    if (!pair) return
    dialog.open({
      key: 'zipnn-delta',
      title: t('zipnnDeltaCompress'),
      content: DialogZipnnDelta,
      contentProps: { models: pair },
      defaultSize: { width: 480, height: 280 },
    })
  }

  return { deltaPair, openDeltaDialog }
}
