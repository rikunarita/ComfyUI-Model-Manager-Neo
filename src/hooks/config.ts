import {
  computed,
  h,
  onMounted,
  onUnmounted,
  readonly,
  ref,
  render as renderVNode,
  watch,
} from 'vue'
import { useI18n } from 'vue-i18n'
import SettingApiKey from 'components/SettingApiKey.vue'
import SettingCardSize from 'components/SettingCardSize.vue'
import { request } from 'hooks/request'
import { defineStore } from 'hooks/store'
import { useToast } from 'hooks/toast'
import { $el, app } from 'scripts/comfyAPI'
import { resolveIcon } from 'utils/iconMap'

export const useConfig = defineStore('config', store => {
  const { t } = useI18n()

  const mobileDeviceBreakPoint = 759
  const isMobile = ref(window.innerWidth < mobileDeviceBreakPoint)

  const checkDeviceType = () => {
    isMobile.value = window.innerWidth < mobileDeviceBreakPoint
  }

  onMounted(() => {
    window.addEventListener('resize', checkDeviceType)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', checkDeviceType)
  })

  const flatLayout = ref(false)

  const defaultCardSizeMap = readonly({
    'size.extraLarge': '240x320',
    'size.large': '180x240',
    'size.medium': '120x160',
    'size.small': '80x120',
  })

  const cardSizeMap = ref<Record<string, string>>({ ...defaultCardSizeMap })
  const cardSizeFlag = ref('size.extraLarge')
  const cardSize = computed(() => {
    const size = cardSizeMap.value[cardSizeFlag.value]
    const [width = '120', height = '240'] = size.split('x')
    return {
      width: parseInt(width),
      height: parseInt(height),
    }
  })

  const config = {
    isMobile,
    gutter: 16,
    defaultCardSizeMap: defaultCardSizeMap,
    cardSizeMap: cardSizeMap,
    cardSizeFlag: cardSizeFlag,
    cardSize: cardSize,
    cardWidth: 240,
    aspect: 7 / 9,
    dialog: {
      showCardSizeSetting: () => {
        store.dialog.open({
          key: 'setting.cardSize',
          title: t('setting.cardSize'),
          content: SettingCardSize,
          defaultSize: {
            width: 500,
            height: 390,
          },
        })
      },
    },
    flat: flatLayout,
    apiKeyInfo: ref<Record<string, string>>({}),
  }

  watch(cardSizeFlag, val => {
    app.ui?.settings.setSettingValue('ModelManager.UI.CardSize', val)
  })

  watch(cardSizeMap, val => {
    app.ui?.settings.setSettingValue('ModelManager.UI.CardSizeMap', JSON.stringify(val))
  })

  useAddConfigSettings(store)

  return config
})

type Config = ReturnType<typeof useConfig>

declare module 'hooks/store' {
  interface StoreProvider {
    config: Config
  }
}

export const configSetting = {
  /**
   * NOTE: the *identifier* no longer says "scan" (the batch-scan feature was
   * removed), but the setting ID string below MUST stay exactly
   * `ModelManager.Scan.excludeScanTypes`: it is the key ComfyUI persists the
   * user's value under, so renaming it would silently orphan every existing
   * installation's saved setting. Same for IncludeHiddenFiles.
   */
  excludeModelTypes: 'ModelManager.Scan.excludeScanTypes',
}

function useAddConfigSettings(store: import('hooks/store').StoreProvider) {
  const { t } = useI18n()
  const { confirm } = useToast()

  /**
   * BUG FIX: this used to build `<i class="pi pi-pencil text-blue-400">`.
   * PrimeIcons shipped with PrimeVue, which this fork removed, and the ComfyUI
   * host stylesheet does not provide it either — so the `<i>` was an empty
   * 16px box that drew nothing. The "edit" and "delete" controls for the
   * Civitai / Hugging Face API keys in ComfyUI's settings panel could not be
   * seen at all (they were only clickable by guessing where the blank gap was).
   *
   * ComfyUI's settings dialog lives outside this extension's Vue app, so the
   * Lucide icon is mounted into the element with Vue's low-level `render()`.
   */
  const iconButton = (opt: {
    icon: string
    colorClass?: string
    onClick: () => void | Promise<void>
  }) => {
    const host = $el(
      `span.inline-flex.h-4.cursor-pointer.items-center${opt.colorClass ? `.${opt.colorClass}` : ''}`,
      { onclick: opt.onClick },
    )
    const icon = resolveIcon(opt.icon)
    if (icon) {
      renderVNode(h(icon, { class: 'size-4' }), host)
    }
    return host
  }

  const setApiKey = async (key: string, setter: (val: string) => void) => {
    store.dialog.open({
      key: `setting.api_key.${key}`,
      title: t(`setting.api_key.${key}`),
      content: SettingApiKey,
      modal: true,
      defaultSize: {
        width: 500,
        height: 200,
      },
      contentProps: {
        keyField: key,
        setter: setter,
      },
    })
  }

  const removeApiKey = async (key: string) => {
    // BUG FIX: resolve with a boolean instead of rejecting on cancel —
    // the rejection previously surfaced as an unhandled promise rejection
    // in the async click handler. Also pass the label for the `deleteAsk`
    // message ("Confirm delete this {0}?") and translated button labels,
    // consistent with the other confirm dialogs.
    const confirmed = await new Promise<boolean>(resolve => {
      confirm.require({
        message: t('deleteAsk', [t('setting.apiKey').toLowerCase()]),
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
        accept: () => resolve(true),
        reject: () => resolve(false),
      })
    })
    if (!confirmed) {
      return
    }
    await request('/download/setting', {
      method: 'POST',
      body: JSON.stringify({ key, value: null }),
    })
  }

  const renderApiKey = (key: string) => {
    return () => {
      const apiKey = store.config.apiKeyInfo.value[key] || 'None'
      const apiKeyDisplayEl = $el('div.text-sm.text-gray-500.flex-1', {
        textContent: apiKey,
      })

      const setter = (val: string) => {
        store.config.apiKeyInfo.value[key] = val
        apiKeyDisplayEl.textContent = val || 'None'
      }
      return $el('div.flex.gap-4', [
        apiKeyDisplayEl,
        iconButton({
          icon: 'pi pi-pencil',
          colorClass: 'text-blue-400',
          onClick: () => {
            setApiKey(key, setter)
          },
        }),
        iconButton({
          icon: 'pi pi-trash',
          colorClass: 'text-red-400',
          onClick: async () => {
            const value = store.config.apiKeyInfo.value[key]
            if (value) {
              await removeApiKey(key)
              setter('')
            }
          },
        }),
      ])
    }
  }

  onMounted(() => {
    // API keys
    app.ui?.settings.addSetting({
      id: 'ModelManager.APIKey.HuggingFace',
      category: [t('modelManager'), t('setting.apiKey'), 'HuggingFace'],
      name: 'HuggingFace API Key',
      defaultValue: undefined,
      type: renderApiKey('huggingface'),
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.APIKey.Civitai',
      category: [t('modelManager'), t('setting.apiKey'), 'Civitai'],
      name: 'Civitai API Key',
      defaultValue: undefined,
      type: renderApiKey('civitai'),
    })

    const defaultCardSize = store.config.defaultCardSizeMap

    app.ui?.settings.addSetting({
      id: 'ModelManager.UI.CardSize',
      category: [t('modelManager'), t('setting.ui'), 'CardSize'],
      name: t('setting.cardSize'),
      defaultValue: 'size.extraLarge',
      type: 'hidden',
      onChange: (val: string) => {
        store.config.cardSizeFlag.value = val
      },
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.UI.CardSizeMap',
      category: [t('modelManager'), t('setting.ui'), 'CardSizeMap'],
      name: t('setting.cardSize'),
      defaultValue: JSON.stringify(defaultCardSize),
      type: 'hidden',
      onChange(value: string) {
        store.config.cardSizeMap.value = JSON.parse(value)
      },
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.UI.Flat',
      category: [t('modelManager'), t('setting.ui'), 'Flat'],
      name: t('setting.useFlatUI'),
      type: 'boolean',
      defaultValue: false,
      onChange(value: boolean) {
        store.dialog.closeAll()
        store.config.flat.value = value
      },
    })

    app.ui?.settings.addSetting({
      id: configSetting.excludeModelTypes,
      category: [t('modelManager'), t('setting.modelList'), 'ExcludeModelTypes'],
      name: t('setting.excludeModelTypes'),
      defaultValue: undefined,
      type: 'text',
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.Scan.IncludeHiddenFiles',
      category: [t('modelManager'), t('setting.modelList'), 'IncludeHiddenFiles'],
      name: t('setting.includeHiddenFiles'),
      defaultValue: false,
      type: 'boolean',
    })
  })
}
