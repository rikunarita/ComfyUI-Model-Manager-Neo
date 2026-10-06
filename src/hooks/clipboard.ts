import { useI18nGlobal } from 'hooks/i18n'
import { useToast } from 'hooks/toast'

/**
 * Clipboard write with toast feedback, shared by the hover-revealed copy
 * buttons of the model detail tables (base info + information).
 */
export const useCopyText = () => {
  const { t } = useI18nGlobal()
  const { toast } = useToast()

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.add({ severity: 'info', summary: t('copiedToClipboard'), life: 2000 })
    } catch (error) {
      toast.add({
        severity: 'warn',
        summary: t('error'),
        detail: (error as Error).message,
        life: 5000,
      })
    }
  }

  return { copyText }
}
