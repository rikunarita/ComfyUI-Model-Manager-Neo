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
import { request } from 'hooks/request'
import { defineStore } from 'hooks/store'
import { useToast } from 'hooks/toast'
import { $el, app } from 'scripts/comfyAPI'
import { resolveIcon } from 'utils/iconMap'

/**
 * Sort values each model-search platform accepts (verified against the live
 * endpoints and the huggingface_hub docstring): offering exactly these keeps
 * the settings combos exhaustive *and* unable to send an invalid key.
 */
export const HF_SORTS = [
  'trending_score',
  'downloads',
  'likes',
  'last_modified',
  'created_at',
] as const
export const MODELSCOPE_SORTS = ['likes', 'downloads', 'last_modified', 'default'] as const
export const CIVITAI_SORTS = [
  'Highest Rated',
  'Most Downloaded',
  'Most Liked',
  'Most Discussed',
  'Most Collected',
  'Most Images',
  'Newest',
  'Oldest',
  'Recently Added',
] as const

/** i18n keys (flat, under the root) for every sort option label. */
export const SORT_LABEL_KEYS: Record<'hf' | 'modelscope' | 'civitai', Record<string, string>> = {
  hf: {
    trending_score: 'sortHfTrending',
    downloads: 'sortHfDownloads',
    likes: 'sortHfLikes',
    last_modified: 'sortHfLastModified',
    created_at: 'sortHfCreatedAt',
  },
  modelscope: {
    likes: 'sortMsLikes',
    downloads: 'sortMsDownloads',
    last_modified: 'sortMsLastModified',
    default: 'sortMsDefault',
  },
  civitai: {
    'Highest Rated': 'sortCivHighestRated',
    'Most Downloaded': 'sortCivMostDownloaded',
    'Most Liked': 'sortCivMostLiked',
    'Most Discussed': 'sortCivMostDiscussed',
    'Most Collected': 'sortCivMostCollected',
    'Most Images': 'sortCivMostImages',
    Newest: 'sortCivNewest',
    Oldest: 'sortCivOldest',
    'Recently Added': 'sortCivRecentlyAdded',
  },
}

/**
 * The custom slot always exists in the map: the card-size editor lists one
 * row per map entry, so without a `size.custom` entry the editor had no
 * input row at all ("the size fields are missing"), and selecting
 * "Custom Size" left `cardSize` resolving `undefined.split('x')`.
 */
const CUSTOM_CARD_SIZE = 'size.custom'
const CUSTOM_CARD_SIZE_DEFAULT = '240x320'

const withCustomSize = (map: Record<string, string>) => ({
  ...map,
  [CUSTOM_CARD_SIZE]: map[CUSTOM_CARD_SIZE] ?? CUSTOM_CARD_SIZE_DEFAULT,
})

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

  // The flat grid is the initial view; the folder explorer is one click away
  // (header toggle or the persisted `ModelManager.UI.Flat` setting).
  const flatLayout = ref(true)

  const defaultCardSizeMap = readonly({
    'size.extraLarge': '240x320',
    'size.large': '180x240',
    'size.medium': '120x160',
    'size.small': '80x120',
  })

  const cardSizeMap = ref<Record<string, string>>(withCustomSize({ ...defaultCardSizeMap }))
  const cardSizeFlag = ref('size.extraLarge')
  const cardSize = computed(() => {
    const size = cardSizeMap.value[cardSizeFlag.value] ?? CUSTOM_CARD_SIZE_DEFAULT
    const [width = '120', height = '240'] = String(size).split('x')
    return {
      width: parseInt(width),
      height: parseInt(height),
    }
  })

  /**
   * Model search sort orders, per platform: every value each platform's API
   * accepts (verified against the live endpoints / client docstrings), so the
   * settings combo can offer them all without ever sending an invalid key.
   */
  const searchSortHf = ref('trending_score')
  const searchSortModelscope = ref('likes')
  const searchSortCivitai = ref('Highest Rated')

  const config = {
    isMobile,
    gutter: 16,
    defaultCardSizeMap: defaultCardSizeMap,
    cardSizeMap: cardSizeMap,
    cardSizeFlag: cardSizeFlag,
    cardSize: cardSize,
    searchSortHf: searchSortHf,
    searchSortModelscope: searchSortModelscope,
    searchSortCivitai: searchSortCivitai,
    cardWidth: 240,
    aspect: 7 / 9,
    dialog: {
      // BUG-FREE BY DESIGN: the component is loaded lazily so this module
      // (which the component itself imports for its store) never forms a
      // static import cycle with it.
      showCardSizeSetting: async () => {
        const { default: SettingCardSize } = await import('components/SettingCardSize.vue')
        store.dialog.open({
          key: 'setting.cardSize',
          title: t('setting.cardSize'),
          content: SettingCardSize,
          contentProps: {
            cardSizeMap,
            defaultCardSizeMap,
            onSave: (map: Record<string, string>) => {
              cardSizeMap.value = map
            },
          },
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
  const { confirm, toast } = useToast()

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
    toast.add({
      severity: 'success',
      summary: t('apiKeyRemoved'),
      detail: t(`setting.api_key.${key}`),
      life: 3000,
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
        if (val) {
          toast.add({
            severity: 'success',
            summary: t('apiKeySaved'),
            detail: t(`setting.api_key.${key}`),
            life: 3000,
          })
        }
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
    // One-time migration: earlier builds (and the upstream project) defaulted
    // the flat layout to OFF and stored that, so the "flat is the default"
    // instruction never reached existing installations. Reset it once, then
    // let the user's own choice stick (the flag below records the migration).
    const FLAT_MIGRATION_KEY = 'ModelManager.UI.FlatDefaultV2'
    app.ui?.settings.addSetting({
      id: FLAT_MIGRATION_KEY,
      category: [t('modelManager'), t('setting.ui'), 'FlatDefaultV2'],
      name: 'flat default migration marker',
      type: 'hidden',
      defaultValue: false,
    })
    if (!app.ui?.settings.getSettingValue<boolean>(FLAT_MIGRATION_KEY)) {
      app.ui?.settings.setSettingValue('ModelManager.UI.Flat', true)
      app.ui?.settings.setSettingValue(FLAT_MIGRATION_KEY, true)
      store.config.flat.value = true
    }

    // API keys
    app.ui?.settings.addSetting({
      id: 'ModelManager.APIKey.Hugging Face',
      category: [t('modelManager'), t('setting.apiKey'), 'Hugging Face'],
      name: 'Hugging Face API Key',
      defaultValue: undefined,
      type: renderApiKey('huggingface'),
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.APIKey.ModelScope',
      category: [t('modelManager'), t('setting.apiKey'), 'ModelScope'],
      name: 'ModelScope API Key',
      defaultValue: undefined,
      type: renderApiKey('modelscope'),
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
        // BUG FIX: a missing / corrupt persisted value made `JSON.parse`
        // yield null, which flowed straight into `Object.entries(null)` in
        // the card-size editor ("Cannot convert undefined or null to
        // object"). Validate every entry and fall back to the defaults.
        let parsed: Record<string, string> | null = null
        try {
          const raw: unknown = JSON.parse(value)
          if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
            const map: Record<string, string> = {}
            for (const [key, val] of Object.entries(raw)) {
              if (typeof val === 'string' && /^\d+x\d+$/.test(val)) map[key] = val
            }
            if (Object.keys(map).length) parsed = map
          }
        } catch {
          parsed = null
        }
        store.config.cardSizeMap.value = withCustomSize(
          parsed ?? { ...store.config.defaultCardSizeMap },
        )
      },
    })

    // Model search sort order: one combo per platform, offering exactly the
    // sort values that platform's API accepts (defaults: Hugging Face
    // trending, ModelScope likes, Civitai highest rated).
    app.ui?.settings.addSetting({
      id: 'ModelManager.Search.SortHuggingFace',
      category: [t('modelManager'), t('setting.search'), 'SortHuggingFace'],
      name: t('setting.searchSortHf'),
      type: 'combo',
      defaultValue: 'trending_score',
      options: HF_SORTS.map(value => ({ text: t(SORT_LABEL_KEYS.hf[value]), value })),
      onChange: (value: string) => {
        store.config.searchSortHf.value = HF_SORTS.includes(value as (typeof HF_SORTS)[number])
          ? value
          : 'trending_score'
      },
    })
    app.ui?.settings.addSetting({
      id: 'ModelManager.Search.SortModelScope',
      category: [t('modelManager'), t('setting.search'), 'SortModelScope'],
      name: t('setting.searchSortMs'),
      type: 'combo',
      defaultValue: 'likes',
      options: MODELSCOPE_SORTS.map(value => ({
        text: t(SORT_LABEL_KEYS.modelscope[value]),
        value,
      })),
      onChange: (value: string) => {
        store.config.searchSortModelscope.value = MODELSCOPE_SORTS.includes(
          value as (typeof MODELSCOPE_SORTS)[number],
        )
          ? value
          : 'likes'
      },
    })
    app.ui?.settings.addSetting({
      id: 'ModelManager.Search.SortCivitai',
      category: [t('modelManager'), t('setting.search'), 'SortCivitai'],
      name: t('setting.searchSortCiv'),
      type: 'combo',
      defaultValue: 'Highest Rated',
      options: CIVITAI_SORTS.map(value => ({ text: t(SORT_LABEL_KEYS.civitai[value]), value })),
      onChange: (value: string) => {
        store.config.searchSortCivitai.value = CIVITAI_SORTS.includes(
          value as (typeof CIVITAI_SORTS)[number],
        )
          ? value
          : 'Highest Rated'
      },
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.Zipnn.AutoCompressUnusedDays',
      category: [t('modelManager'), t('setting.zipnn'), 'AutoCompressUnusedDays'],
      name: t('setting.autoCompressUnusedDays'),
      type: 'number',
      defaultValue: 0,
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.Zipnn.AutoCompressOnDownload',
      category: [t('modelManager'), t('setting.zipnn'), 'AutoCompressOnDownload'],
      name: t('setting.autoCompressOnDownload'),
      type: 'boolean',
      defaultValue: false,
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.Download.PauseDuringPrompt',
      category: [t('modelManager'), t('setting.download'), 'PauseDuringPrompt'],
      name: t('setting.pauseDuringPrompt'),
      type: 'boolean',
      defaultValue: false,
    })

    app.ui?.settings.addSetting({
      id: 'ModelManager.UI.Flat',
      category: [t('modelManager'), t('setting.ui'), 'Flat'],
      name: t('setting.useFlatUI'),
      type: 'boolean',
      defaultValue: true,
      onChange(value: boolean) {
        store.dialog.closeAll()
        store.config.flat.value = value
      },
    })

    // Search-result platform visibility (the multi-platform model search).
    app.ui?.settings.addSetting({
      id: 'ModelManager.Search.HideHuggingFace',
      category: [t('modelManager'), t('setting.search'), 'HideHuggingFace'],
      name: t('setting.hideSearchHf'),
      type: 'boolean',
      defaultValue: false,
    })
    app.ui?.settings.addSetting({
      id: 'ModelManager.Search.HideModelScope',
      category: [t('modelManager'), t('setting.search'), 'HideModelScope'],
      name: t('setting.hideSearchMs'),
      type: 'boolean',
      defaultValue: false,
    })
    app.ui?.settings.addSetting({
      id: 'ModelManager.Search.HideCivitai',
      category: [t('modelManager'), t('setting.search'), 'HideCivitai'],
      name: t('setting.hideSearchCivitai'),
      type: 'boolean',
      defaultValue: false,
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
