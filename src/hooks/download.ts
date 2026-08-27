import { useLoading } from 'hooks/loading'
import { request } from 'hooks/request'
import { defineStore } from 'hooks/store'
import { useToast } from 'hooks/toast'
import { onBeforeMount, onMounted, ref } from 'vue'
import { api } from 'scripts/comfyAPI'
import { DownloadTaskOptions, SelectOptions, VersionModel, VersionModelFile } from 'types/typings'
import { genFileSelectionItem, createDirectFileModel, isDirectFileUrl } from 'utils/model'

type WithSelection<T> = SelectOptions & { item: T }
type FileSelectionVersionModel = VersionModel & {
  currentFileId?: number
  selectionFiles?: WithSelection<VersionModelFile>[]
}

export const useDownload = defineStore('download', (store) => {
  const { toast } = useToast()
  const loading = useLoading()
  const taskList = ref<DownloadTaskOptions[]>([])

  const createTaskItem = (item: DownloadTaskOptions): DownloadTaskOptions => {
    return { ...item }
  }

  const refresh = async () => {
    loading.show()
    try {
      const resData = await request('/download/task')
      taskList.value = (resData as DownloadTaskOptions[]).map((item) => {
        return createTaskItem(item)
      })
    } catch (err: any) {
      console.error('Failed to refresh download tasks:', err)
      // エラー時はタスクリストを空にしてUIフリーズを防ぐ
      taskList.value = []
    } finally {
      loading.hide()
    }
  }

  const init = async () => {
    try {
      const res = await request('/download/init', { method: 'POST' })
      store.config.apiKeyInfo.value = res
    } catch (err: any) {
      console.error('Failed to init download settings:', err)
      store.config.apiKeyInfo.value = {}
    }
  }

  onBeforeMount(() => {
    init()

    api.addEventListener('reconnected', () => {
      refresh()
    })

    api.addEventListener('fetch_download_task_list', (event) => {
      const data = event.detail as DownloadTaskOptions[]
      taskList.value = data.map((item) => {
        return createTaskItem(item)
      })
    })

    api.addEventListener('create_download_task', (event) => {
      const item = event.detail as DownloadTaskOptions
      taskList.value.unshift(createTaskItem(item))
    })

    api.addEventListener('update_download_task', (event) => {
      const item = event.detail as DownloadTaskOptions
      for (const task of taskList.value) {
        if (task.taskId === item.taskId) {
          if (item.error) {
            toast.add({
              severity: 'error',
              summary: 'Error',
              detail: item.error,
              life: 15000,
            })
            item.error = undefined
          }
          Object.assign(task, createTaskItem(item))
        }
      }
    })

    api.addEventListener('delete_download_task', (event) => {
      const taskId = event.detail as string
      taskList.value = taskList.value.filter((item) => item.taskId !== taskId)
    })

    api.addEventListener('complete_download_task', (event) => {
      const taskId = event.detail as string
      const task = taskList.value.find((item) => item.taskId === taskId)
      taskList.value = taskList.value.filter((item) => item.taskId !== taskId)
      toast.add({
        severity: 'success',
        summary: 'Success',
        detail: `${task?.fullname} Download completed`,
        life: 2000,
      })
      store.models.refresh()
    })
  })

  onMounted(() => {
    refresh()
  })

  return { data: taskList, refresh }
})

declare module 'hooks/store' {
  interface StoreProvider {
    download: ReturnType<typeof useDownload>
  }
}

export const useModelSearch = () => {
  const loading = useLoading()
  const { toast } = useToast()
  const data = ref<WithSelection<FileSelectionVersionModel>[]>()
  const current = ref<string | number>()
  const currentModel = ref<FileSelectionVersionModel>()

  const handleSearchByUrl = async (url: string, modelType?: string) => {
    if (!url) {
      return Promise.resolve([])
    }

    loading.show()
    if (isDirectFileUrl(url)) {
      try {
        const directModel = createDirectFileModel(url, modelType)
        const resolvedItem = genFileSelectionItem(directModel)
        data.value = [[
          {
            label: directModel.shortname,
            value: directModel.id,
            item: resolvedItem,
            command() {
              current.value = directModel.id
            },
          }
        ]]
        current.value = data.value[0]?.value
        currentModel.value = data.value[0]?.item
        loading.hide()
        return [directModel]
      } catch (error) {
        console.error('Error processing direct file URL:', error)
        loading.hide()
        toast.add({
          severity: 'error',
          summary: 'Error',
          detail: `Failed to process direct file URL: ${error instanceof Error ? error.message : 'Unknown error'}`,
          life: 5000,
        })
        return []
      }
    }

    return request(`/model-info?model-page=${encodeURIComponent(url)}`, {})
      .then((resData: VersionModel[]) => {
        data.value = resData.map((item) => {
          const resolvedItem = genFileSelectionItem(item)
          return {
            label: item.shortname,
            value: item.id,
            item: resolvedItem,
            command() {
              current.value = item.id
            },
          }
        })
        current.value = data.value[0]?.value
        currentModel.value = data.value[0]?.item
        if (resData.length === 0) {
          toast.add({
            severity: 'warn',
            summary: 'No Model Found',
            detail: `No model found for ${url}`,
            life: 3000,
          })
        }
        return resData
      })
      .catch((err) => {
        toast.add({
          severity: 'error',
          summary: 'Error',
          detail: err.message,
          life: 15000,
        })
        return []
      })
      .finally(() => loading.hide())
  }

  return { data, current, currentModel, search: handleSearchByUrl }
}
