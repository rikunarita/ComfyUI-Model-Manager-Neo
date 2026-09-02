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
                  v-model="item.width"
                  class="flex-1"
                  :step="10"
                  :min="80"
                  :max="320"
                />
                <span class="w-10 text-right text-sm text-mm-muted-fg">{{ item.width }}</span>
              </div>
            </td>
            <td class="py-3">
              <div class="flex items-center gap-4">
                <Slider
                  v-model="item.height"
                  class="flex-1"
                  :step="10"
                  :min="80"
                  :max="320"
                />
                <span class="w-10 text-right text-sm text-mm-muted-fg">{{ item.height }}</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="flex justify-between px-4 py-4">
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
import { Button } from 'components/ui/button'
import { Slider } from 'components/ui/slider'
import { useConfig } from 'hooks/config'
import { useDialog } from 'hooks/dialog'
import { onMounted, ref } from 'vue'

const { cardSizeMap, defaultCardSizeMap } = useConfig()
const dialog = useDialog()

const sizeList = ref<Array<{ id: string; name: string; width: number; height: number }>>([])

const resolveSizeMap = (sizeMap: Record<string, string>) => {
  return Object.entries(sizeMap).map(([key, value]) => {
    const [width, height] = value.split('x')
    return {
      id: key,
      name: key,
      width: parseInt(width),
      height: parseInt(height),
    }
  })
}

const resolveSizeList = (
  sizeList: { name: string; width: number; height: number }[],
) => {
  return Object.fromEntries(
    sizeList.map(({ name, width, height }) => {
      return [name, [width, height].join('x')]
    }),
  )
}

onMounted(() => {
  sizeList.value = resolveSizeMap(cardSizeMap.value)
})

const handleReset = () => {
  sizeList.value = resolveSizeMap(defaultCardSizeMap.value)
}

const handleCancelEditor = () => {
  sizeList.value = resolveSizeMap(cardSizeMap.value)
  dialog.close()
}

const handleSaveSizeMap = () => {
  cardSizeMap.value = resolveSizeList(sizeList.value)
  dialog.close()
}
</script>
