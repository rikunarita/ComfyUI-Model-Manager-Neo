<template>
  <div class="flex h-full flex-col">
    <div class="flex-1 px-4">
      <table class="w-full border-collapse">
        <thead>
          <tr class="border-b border-mm-border text-left text-sm font-medium text-mm-muted-fg">
            <th class="py-3 pr-4">{{ $t('name') }}</th>
            <th class="min-w-36 py-3 pr-4">{{ $t('width') }}</th>
            <th class="min-w-36 py-3">{{ $t('height') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in sizeList"
            :key="item.id"
            class="border-b border-mm-border last:border-0"
          >
            <td class="py-3 pr-4 text-sm text-mm-fg">{{ $t(item.name) }}</td>
            <td class="py-3 pr-4">
              <div class="flex items-center gap-4">
                <Slider
                  :model-value="[item.width]"
                  class="flex-1"
                  :step="10"
                  :min="80"
                  :max="320"
                  @update:model-value="
                    (val?: number[]) => {
                      if (val) item.width = val[0]
                    }
                  "
                />
                <span class="w-10 text-right text-sm text-mm-muted-fg">{{ item.width }}</span>
              </div>
            </td>
            <td class="py-3">
              <div class="flex items-center gap-4">
                <Slider
                  :model-value="[item.height]"
                  class="flex-1"
                  :step="10"
                  :min="80"
                  :max="320"
                  @update:model-value="
                    (val?: number[]) => {
                      if (val) item.height = val[0]
                    }
                  "
                />
                <span class="w-10 text-right text-sm text-mm-muted-fg">{{ item.height }}</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="flex justify-between p-4">
      <div></div>
      <div class="flex gap-2">
        <Button variant="outline" @click="handleReset">
          <RefreshCw class="size-4" />
          {{ $t('reset') }}
        </Button>
        <Button variant="outline" @click="handleCancelEditor">
          {{ $t('cancel') }}
        </Button>
        <Button @click="handleSaveSizeMap">
          {{ $t('save') }}
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { onMounted, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from 'components/ui/button'
import { Slider } from 'components/ui/slider'
import { useDialog } from 'hooks/dialog'
import { useToast } from 'hooks/toast'

/**
 * The store slices are injected by the opener (`showCardSizeSetting`) so this
 * component never imports `hooks/config` — which loads the component — and
 * the two can never form an import cycle.
 */
interface Props {
  cardSizeMap: Ref<Record<string, string>>
  defaultCardSizeMap: Record<string, string>
  /** Writes the edited map back into the config store (owned by the opener). */
  onSave: (map: Record<string, string>) => void
}
const props = defineProps<Props>()

const { t } = useI18n()
const { toast } = useToast()
const dialog = useDialog()

const sizeList = ref<Array<{ id: string; name: string; width: number; height: number }>>([])

const resolveSizeMap = (sizeMap: Record<string, string> | null | undefined) => {
  // The custom slot is always editable: even a map persisted before the
  // `size.custom` entry existed gets its row (seeded with the default).
  const source = { 'size.custom': '240x320', ...(sizeMap ?? {}) }
  return Object.entries(source).map(([key, value]) => {
    const [width, height] = String(value).split('x')
    return {
      id: key,
      name: key,
      width: parseInt(width),
      height: parseInt(height),
    }
  })
}

const resolveSizeList = (sizeList: { name: string; width: number; height: number }[]) => {
  return Object.fromEntries(
    sizeList.map(({ name, width, height }) => {
      return [name, [width, height].join('x')]
    }),
  )
}

onMounted(() => {
  sizeList.value = resolveSizeMap(props.cardSizeMap.value)
})

const handleReset = () => {
  sizeList.value = resolveSizeMap(props.defaultCardSizeMap)
  toast.add({ severity: 'info', summary: t('cardSizeReset'), life: 2500 })
}

const handleCancelEditor = () => {
  sizeList.value = resolveSizeMap(props.cardSizeMap.value)
  dialog.close()
}

const handleSaveSizeMap = () => {
  props.onSave(resolveSizeList(sizeList.value))
  dialog.close()
  toast.add({ severity: 'success', summary: t('cardSizeSaved'), life: 2500 })
}
</script>
