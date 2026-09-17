import DialogModelDetail from 'components/DialogModelDetail.vue'
import { useDialog } from 'hooks/dialog'
import { type BaseModel } from 'types/typings'
import { genModelKey } from 'utils/model'

/**
 * Opens the model detail window.
 *
 * Split out of `hooks/model` to break the module cycle
 * hooks/model → DialogModelDetail.vue → ModelContent.vue → hooks/model:
 * the models store no longer needs to know the detail component, while the
 * component side keeps importing the store exactly as before.
 */
export const useModelDetail = () => {
  const dialog = useDialog()

  const openModelDetail = (model: BaseModel) => {
    // `basename` already excludes the extension, so the previous
    // `basename.replace(extension, '')` only ever did damage: String.replace
    // swaps the FIRST occurrence, so a file named
    // "foo.safetensors.safetensors" opened a dialog titled "foo".
    const filename = model.basename

    dialog.open({
      key: genModelKey(model),
      title: filename,
      content: DialogModelDetail,
      contentProps: { model: model },
    })
  }

  return { openModelDetail }
}
