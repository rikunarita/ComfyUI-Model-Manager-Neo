<template>
  <div class="flex h-full flex-col gap-4 p-4">
    <ResponseInput
      v-model.trim="name"
      :placeholder="$t('folderNamePlaceholder')"
      @keyup.enter="submit"
    ></ResponseInput>
    <div class="-mt-2 text-xs text-mm-muted-fg">
      {{ $t('folderCreateHint', { path: targetLabel }) }}
    </div>
    <div class="mt-auto flex justify-end gap-2">
      <Button variant="secondary" @click="close">{{ $t('cancel') }}</Button>
      <Button :disabled="!name" @click="submit">
        <FolderPlus class="size-4" />
        {{ $t('addFolder') }}
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FolderPlus } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ResponseInput from 'components/ResponseInput.vue'
import { Button } from 'components/ui/button'
import { useDialog } from 'hooks/dialog'
import { useModels } from 'hooks/model'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'

interface Props {
  type: string
  pathIndex: number
  subFolder: string
}

const props = defineProps<Props>()

const { t } = useI18n()
const { toast } = useToast()
const dialog = useDialog()
const { refreshFolder } = useModels()

const name = ref<string>()

const targetLabel = computed(
  () => [props.type, props.subFolder].filter(Boolean).join('/') || props.type,
)

const close = () => {
  dialog.close({ key: 'create-folder' })
}

const submit = async () => {
  const folderName = name.value
  if (!folderName) return
  try {
    const res = (await request('/create-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: props.type,
        pathIndex: props.pathIndex,
        subFolder: props.subFolder,
        name: folderName,
      }),
    })) as { success?: boolean; error?: string }
    if (!res?.success) {
      throw new Error(res?.error ?? 'unknown error')
    }
    toast.add({ severity: 'success', summary: t('folderCreated'), detail: folderName, life: 2500 })
    await refreshFolder(props.type)
    close()
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: error instanceof Error ? error.message : String(error),
      life: 8000,
    })
  }
}
</script>
