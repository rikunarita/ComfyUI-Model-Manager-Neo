import { defineStore } from 'hooks/store'
import { useLoading } from 'hooks/loading'
import { useToast } from 'hooks/toast'
import { castArray, cloneDeep } from 'lodash'
import { TreeNode } from 'primevue/treenode'
import { api, app } from 'scripts/comfyAPI'
import { BaseModel, Model, SelectEvent, WithResolved } from 'types/typings'
import { bytesToSize, formatDate, previewUrlToFile } from 'utils/common'
import { ModelGrid } from 'utils/legacy'
import { genModelKey, resolveModelTypeLoader } from 'utils/model'
import {
  computed,
  inject,
  type InjectionKey,
  MaybeRefOrGetter,
  onMounted,
  provide,
  type Ref,
  ref,
  toRaw,
  toValue,
  unref,
} from 'vue'
import { useI18n } from 'vue-i18n'
import { request } from 'hooks/request'
import { configSetting } from 'hooks/config'
import DialogModelDetail from 'components/DialogModelDetail.vue'

const systemStat = ref()

type ModelFolder = Record<string, string[]>

const modelFolderProvideKey = Symbol('modelFolder') as InjectionKey<
  Ref<ModelFolder>
>

export const genModelFullName = (model: BaseModel, splitter = '/') => {
  return [model.subFolder, `${model.basename}${model.extension}`]
    .filter(Boolean)
    .join(splitter)
}

export const genModelUrl = (model: BaseModel) => {
  const fullname = genModelFullName(model)
  return `/model/${model.type}/${model.pathIndex}/${fullname}`
}

export const useModels = defineStore('models', (store) => {
  const { toast, confirm } = useToast()
  const { t } = useI18n()
  const loading = useLoading()
  const folders = ref<ModelFolder>({})
  const initialized = ref(false)

  const refreshFolders = async () => {
    return request('/models')
      .then((resData) => {
        folders.value = resData
        initialized.value = true
      })
      .catch((err) => {
        console.error('Failed to refresh folders:', err)
        toast.add({
          severity: 'error',
          summary: 'Error',
          detail: `Failed to load folders: ${err.message}`,
          life: 5000,
        })
      })
  }

  provide(modelFolderProvideKey, folders)

  const models = ref<Record<string, Model[]>>({})

  const refreshModels = async (folder: string) => {
    loading.show(folder)
    return request(`/models/${folder}`)
      .then((resData) => {
        models.value[folder] = resData
        return resData
      })
      .catch((err) => {
        console.error(`Failed to refresh models for ${folder}:`, err)
      })
      .finally(() => {
        loading.hide(folder)
      })
  }

  const refreshAllModels = async (force = false) => {
    const forceRefresh = force ? refreshFolders() : Promise.resolve()
    models.value = {}
    const excludeScanTypes = app.ui?.settings.getSettingValue<string>(
      configSetting.excludeScanTypes,
    )
    const customBlackList =
      excludeScanTypes
        ?.split(',')
        .map((type) => type.trim())
        .filter(Boolean) ?? []

    await forceRefresh.then(() =>
      Promise.allSettled(
        Object.keys(folders.value)
          .filter((folder) => !customBlackList.includes(folder))
          .map(refreshModels),
      ),
    )
  }

  const updateModel = async (
    model: BaseModel,
    data: WithResolved<BaseModel>,
  ) => {
    const updateData = new FormData()
    let oldKey: string | null = null
    let needUpdate = false

    // Check current preview
    if (model.preview !== data.preview) {
      const preview = data.preview
      // 【修正】プレビューがない場合に文字列 "undefined" を送るのをやめ、単にセットしない
      if (preview && preview !== 'no-preview.png') {
        try {
          const previewFile = await previewUrlToFile(data.preview as string)
          updateData.set('previewFile', previewFile)
        } catch (e) {
          console.warn('Failed to convert preview URL to file:', e)
        }
      }
      needUpdate = true
    }

    // Check current description
    if (model.description !== data.description) {
      updateData.set('description', data.description)
      needUpdate = true
    }

    // Check current name and pathIndex
    if (
      model.subFolder !== data.subFolder ||
      model.pathIndex !== data.pathIndex
    ) {
      oldKey = genModelKey(model)
      updateData.set('type', data.type)
      updateData.set('pathIndex', data.pathIndex.toString())
      updateData.set('fullname', genModelFullName(data as BaseModel))
      needUpdate = true
    }

    if (!needUpdate) {
      return
    }

    loading.show()
    await request(genModelUrl(model), {
      method: 'PUT',
      body: updateData,
    })
      .catch((err) => {
        const error_message = err.message ?? err.error
        toast.add({
          severity: 'error',
          summary: 'Error',
          detail: `Failed to update model: ${error_message}`,
          life: 15000,
        })
        throw new Error(error_message)
      })
      .finally(() => {
        loading.hide()
      })

    if (oldKey) {
      store.dialog.close({ key: oldKey })
    }
    refreshModels(data.type)
  }

  const deleteModel = async (model: BaseModel) => {
    return new Promise((resolve) => {
      confirm.require({
        message: t('deleteAsk', [t('model').toLowerCase()]),
        header: 'Danger',
        icon: 'pi pi-info-circle',
        rejectProps: {
          label: t('cancel'),
          severity: 'secondary',
          outlined: true,
        },
        acceptProps: {
          label: t('delete'),
          severity: 'danger',
        },
        accept: () => {
          const dialogKey = genModelKey(model)
          loading.show()
          request(genModelUrl(model), {
            method: 'DELETE',
          })
            .then(() => {
              toast.add({
                severity: 'success',
                summary: 'Success',
                detail: `${model.basename} Deleted`,
                life: 2000,
              })
              store.dialog.close({ key: dialogKey })
              return refreshModels(model.type)
            })
            .then(() => {
              resolve(void 0)
            })
            .catch((e) => {
              toast.add({
                severity: 'error',
                summary: 'Error',
                detail: e.message ?? 'Failed to delete model',
                life: 15000,
              })
            })
            .finally(() => {
              loading.hide()
            })
        },
        reject: () => {
          resolve(void 0)
        },
      })
    })
  }

  function openModelDetail(model: BaseModel) {
    const filename = model.basename.replace(model.extension, '')
    store.dialog.open({
      key: genModelKey(model),
      title: filename,
      content: DialogModelDetail,
      contentProps: { model: model },
    })
  }

  function getFullPath(model: BaseModel) {
    const fullname = genModelFullName(model)
    const prefixPath = folders.value[model.type]?.[model.pathIndex]
    return [prefixPath, fullname].filter(Boolean).join('/')
  }

  onMounted(() => {
    api.getSystemStats().then((res) => {
      systemStat.value = res
    })
  })

  return {
    initialized: initialized,
    folders: folders,
    data: models,
    refresh: refreshAllModels,
    remove: deleteModel,
    update: updateModel,
    openModelDetail: openModelDetail,
    getFullPath: getFullPath,
  }
})

declare module 'hooks/store' {
  interface StoreProvider {
    models: ReturnType<typeof useModels>
  }
}

export const useModelNodeAction = () => {
  const { t } = useI18n()
  const { toast, wrapperToastError } = useToast()

  const createNode = (model: BaseModel, options: Record<string, any> = {}) => {
    const nodeType = resolveModelTypeLoader(model.type)
    if (!nodeType) {
      throw new Error(t('unSupportedModelType', [model.type]))
    }
    const node = window.LiteGraph.createNode(nodeType, null, options)
    const widgetIndex = node.widgets.findIndex((w) => w.type === 'combo')
    if (widgetIndex > -1) {
      node.widgets[widgetIndex].value = genModelFullName(model)
    }
    return node
  }

  const dragToAddModelNode = wrapperToastError(
    (model: BaseModel, event: DragEvent) => {
      const removeEmbeddingExtension = true
      const strictDragToAdd = false
      const splitter = systemStat.value?.system.os === 'nt' ? '\\' : '/'

      ModelGrid.dragAddModel(
        event,
        model.type,
        genModelFullName(model, splitter),
        removeEmbeddingExtension,
        strictDragToAdd,
      )
    },
  )

  const addModelNode = wrapperToastError((model: BaseModel) => {
    const selectedNodes = app.canvas.selected_nodes
    const firstSelectedNode = Object.values(selectedNodes)[0]
    const offset = 25
    const pos = firstSelectedNode
      ? [firstSelectedNode.pos[0] + offset, firstSelectedNode.pos[1] + offset]
      : app.canvas.canvas_mouse
    const node = createNode(model, { pos })
    app.graph.add(node)
    app.canvas.selectNode(node)
  })

  const copyModelNode = wrapperToastError((model: BaseModel) => {
    const node = createNode(model)
    app.canvas.copyToClipboard([node])
    toast.add({
      severity: 'success',
      summary: 'Success',
      detail: t('modelCopied'),
      life: 2000,
    })
  })

  const loadPreviewWorkflow = wrapperToastError(async (model: BaseModel) => {
    const previewUrl = model.preview as string
    const response = await fetch(previewUrl)
    const data = await response.blob()
    const type = data.type
    const extension = type.split('/').pop()
    const file = new File([data], `${model.basename}.${extension}`, { type })
    app.handleFile(file)
  })

  return {
    addModelNode,
    dragToAddModelNode,
    copyModelNode,
    loadPreviewWorkflow,
  }
}
