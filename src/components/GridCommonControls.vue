<script setup lang="ts">
import { BrushCleaning } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import { useGridSelectOptions } from 'hooks/gridOptions'
import { type SelectOptions } from 'types/typings'

/**
 * The control trio both grid toolbars share: sort-order select, card-size
 * select and the hygiene-scan button. The sort order stays owned by the
 * parent view (each layout sorts its own list), the card-size pair comes
 * straight from the shared composable / config store.
 */
interface Props {
  sortOrder: string
  sortOrderOptions: SelectOptions[]
}
defineProps<Props>()

const sortOrderModel = defineModel<string>('sortOrder', { required: true })

const emits = defineEmits<{ hygiene: [] }>()

const { t } = useI18n()
const { cardSizeOptions, cardSizeFlag } = useGridSelectOptions()
</script>

<template>
  <ResponseSelect
    v-model="sortOrderModel"
    class="flex-1"
    :items="sortOrderOptions"
  ></ResponseSelect>
  <ResponseSelect v-model="cardSizeFlag" class="flex-1" :items="cardSizeOptions"></ResponseSelect>
  <Button
    variant="secondary"
    size="icon"
    :title="t('hygiene')"
    :aria-label="t('hygiene')"
    @click="emits('hygiene')"
  >
    <BrushCleaning class="size-4" />
  </Button>
</template>
