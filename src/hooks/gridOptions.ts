import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useConfig } from 'hooks/config'
import { recentRank } from 'hooks/recent'

/**
 * The sort-order and card-size selects of the two grid layouts (flat and
 * folder view) are the same control pair with the same options, so both
 * toolbars build them from this one composable instead of keeping byte
 * identical copies in sync by hand.
 */
export const useGridSelectOptions = () => {
  const { t } = useI18n()
  const { cardSizeMap, cardSizeFlag, dialog: settings } = useConfig()

  const sortOrder = ref('name')
  const sortOrderOptions = ref(
    ['name', 'size', 'created', 'modified', 'recent'].map(key => {
      return {
        label: t(`sort.${key}`),
        value: key,
        icon: key === 'name' ? 'pi pi-sort-alpha-down' : 'pi pi-sort-amount-down',
        command: () => {
          sortOrder.value = key
        },
      }
    }),
  )

  const cardSizeOptions = computed(() => {
    const customSize = 'size.custom'
    return Object.keys(cardSizeMap.value).map(key => {
      return {
        label: t(key),
        value: key,
        command: () => {
          if (key === customSize) {
            // Apply the custom slot AND open its editor (the map always
            // carries a `size.custom` entry, so the editor has a row for it).
            cardSizeFlag.value = key
            settings.showCardSizeSetting()
          } else {
            cardSizeFlag.value = key
          }
        },
      }
    })
  })

  /** Comparator for the "recently used" order (never-used models last). */
  const compareRecent = (aKey: string, bKey: string) => recentRank(bKey) - recentRank(aKey)

  return { sortOrder, sortOrderOptions, cardSizeOptions, cardSizeFlag, compareRecent }
}
