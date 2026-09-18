<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from 'components/ui/button'
import { Input } from 'components/ui/input'
import { addCollection, collectionState, type SmartCollectionQuery } from 'hooks/collections'
import { useDialog } from 'hooks/dialog'
import { useToast } from 'hooks/toast'

interface Props {
  query: SmartCollectionQuery
}
const props = defineProps<Props>()

const { t } = useI18n()
const { toast } = useToast()
const dialog = useDialog()

const name = ref<string>()

const handleSave = () => {
  const label = name.value?.trim()
  if (!label) {
    toast.add({ severity: 'warn', summary: t('validation.nameRequired'), life: 4000 })
    return
  }
  addCollection(label, props.query)
  collectionState.activeId = collectionState.collections.at(-1)?.id ?? null
  dialog.close()
}
</script>

<template>
  <div class="flex flex-col gap-4 px-5 pb-5">
    <Input
      v-model="name"
      :placeholder="t('collectionsNamePlaceholder')"
      @keydown.enter="handleSave"
    />
    <div class="flex justify-end">
      <Button @click="handleSave">{{ $t('save') }}</Button>
    </div>
  </div>
</template>
