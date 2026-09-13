import { CircleCheck, CircleX, Info, TriangleAlert } from '@lucide/vue'
import { reactive } from 'vue'
import { type Component } from 'vue'
import { toast as sonnerToast } from 'vue-sonner'
import { useI18nGlobal } from 'hooks/i18n'

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

export type ToastSeverity = 'success' | 'info' | 'warn' | 'error'

export interface ToastAddOptions {
  severity?: ToastSeverity
  summary?: string
  detail?: string
  life?: number
  /** Override the severity icon; pass `null` for no icon at all. */
  icon?: Component | null
  /** Optional right-hand button inside the toast. */
  action?: { label: string; onClick: () => void }
}

/**
 * Severity → icon. The toasts are the extension's primary feedback channel, so
 * every one of them carries a recognisable glyph tinted by the severity class
 * in `Sonner.vue` (vue-sonner runs `unstyled`, therefore the icon component is
 * handed to it explicitly and only the colour/size come from CSS).
 */
const SEVERITY_ICON: Record<ToastSeverity, Component> = {
  success: CircleCheck,
  error: CircleX,
  warn: TriangleAlert,
  info: Info,
}

export const useToast = () => {
  const toast = {
    add: (opts: ToastAddOptions) => {
      const { severity = 'info', summary, detail, life = 4500, icon, action } = opts
      const message = summary || detail || ''
      const description = summary && detail ? detail : undefined
      const shared = {
        description,
        duration: life,
        icon: icon === null ? undefined : (icon ?? SEVERITY_ICON[severity]),
        action: action ? { label: action.label, onClick: action.onClick } : undefined,
      }

      switch (severity) {
        case 'success':
          sonnerToast.success(message, shared)
          break
        case 'error':
          sonnerToast.error(message, shared)
          break
        case 'warn':
          sonnerToast.warning(message, shared)
          break
        default:
          sonnerToast(message, shared)
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
    // Resolved through the global composer: `wrapperToastError` also wraps
    // module-level listeners (websocket handlers) that run outside any
    // component, where `useI18n()` cannot resolve.
    const { t } = useI18nGlobal()
    const showToast = (error: Error) => {
      toast.add({
        severity: 'error',
        summary: t('error'),
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
