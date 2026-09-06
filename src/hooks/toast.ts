import { reactive, ref } from 'vue'
import { toast as sonnerToast } from 'vue-sonner'

// Confirm dialog state (reactive store)
export interface ConfirmOptions {
  message: string
  header?: string
  icon?: string
  rejectProps?: { label?: string; severity?: string; outlined?: boolean }
  acceptProps?: { label?: string; severity?: string }
  accept: () => void
  reject: () => void
}

export const confirmState = reactive<{
  visible: boolean
  options: ConfirmOptions | null
}>({
  visible: false,
  options: null,
})

export const useToast = () => {
  const toast = {
    add: (opts: {
      severity?: 'success' | 'info' | 'warn' | 'error'
      summary?: string
      detail?: string
      life?: number
    }) => {
      const { severity = 'info', summary, detail, life = 3000 } = opts
      const message = summary || detail || ''
      const description = summary && detail ? detail : undefined

      switch (severity) {
        case 'success':
          sonnerToast.success(message, { description, duration: life })
          break
        case 'error':
          sonnerToast.error(message, { description, duration: life })
          break
        case 'warn':
          sonnerToast.warning(message, { description, duration: life })
          break
        default:
          sonnerToast(message, { description, duration: life })
      }
    },
  }

  const confirm = {
    require: (opts: ConfirmOptions) => {
      confirmState.options = opts
      confirmState.visible = true
    },
  }

  const wrapperToastError = <T extends CallableFunction>(callback: T): T => {
    const showToast = (error: Error) => {
      toast.add({
        severity: 'error',
        summary: 'Error',
        detail: error.message,
        life: 15000,
      })
    }

    const isAsync = callback.constructor.name === 'AsyncFunction'

    let wrapperExec: any

    if (isAsync) {
      wrapperExec = (...args: any[]) => callback(...args).catch(showToast)
    } else {
      wrapperExec = (...args: any[]) => {
        try {
          return callback(...args)
        } catch (error) {
          showToast(error as Error)
        }
      }
    }

    return wrapperExec
  }

  return { toast, wrapperToastError, confirm }
}
