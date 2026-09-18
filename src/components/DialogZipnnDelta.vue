<template>
  <div class="flex h-full flex-col gap-4 p-4">
    <p class="text-sm text-mm-muted-fg">{{ $t('zipnnDeltaHint') }}</p>

    <ResponseSelect v-model="baseIndex" class="w-full" :items="baseOptions">
      <template #prefix>
        <span>{{ $t('zipnnDeltaBase') }}</span>
      </template>
    </ResponseSelect>

    <div class="text-sm">
      <span class="text-mm-muted-fg">{{ $t('zipnnDeltaFt') }}:</span>
      {{ fullName(ftModel) }}
    </div>

    <div class="mt-auto flex justify-end gap-2">
      <Button variant="secondary" @click="close">{{ $t('cancel') }}</Button>
      <Button @click="submit">
        <GitCompareArrows class="size-4" />
        {{ $t('zipnnDeltaCompress') }}
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { GitCompareArrows } from '@lucide/vue'
import { computed, ref } from 'vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import { useDialog } from 'hooks/dialog'
import { genModelFullName } from 'hooks/model'
import { startZipnnDelta } from 'hooks/zipnn'
import { type BaseModel } from 'types/typings'
import { genModelKey } from 'utils/model'

interface Props {
  models: BaseModel[]
}

const props = defineProps<Props>()

const dialog = useDialog()

/** Index (into `models`) of the base model; the other one is the fine-tune. */
const baseIndex = ref('0')

const fullName = (model: BaseModel) => `${model.type}/${genModelFullName(model)}`

const baseOptions = computed(() =>
  props.models.map((model, index) => ({
    label: fullName(model),
    value: String(index),
    command: () => {
      baseIndex.value = String(index)
    },
  })),
)

const baseModel = computed(() => props.models[Number(baseIndex.value)] ?? props.models[0])
const ftModel = computed(() => props.models.find(m => m !== baseModel.value) ?? props.models[1])

const close = () => {
  dialog.close({ key: 'zipnn-delta' })
}

const submit = () => {
  const base = baseModel.value
  const ft = ftModel.value
  if (!base || !ft) return
  close()
  void startZipnnDelta(
    { type: base.type, pathIndex: base.pathIndex, fullname: genModelFullName(base) },
    { type: ft.type, pathIndex: ft.pathIndex, fullname: genModelFullName(ft) },
    genModelKey(ft),
  )
}
</script>
