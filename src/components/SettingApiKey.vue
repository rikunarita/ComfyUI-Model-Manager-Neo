<template>
  <div class="p-4">
    <Input v-model="content" class="w-full" :placeholder="$t('setNewApiKey')" autocomplete="off" />
    <div class="mt-4 flex items-center justify-between">
      <div>
        <span v-show="showError" class="text-sm text-mm-danger">{{ $t('apiKeyNotEmpty') }}</span>
      </div>
      <Button autofocus @click="saveKeybinding">{{ $t('save') }}</Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, toValue } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from 'components/ui/button'
import { Input } from 'components/ui/input'
import { useDialog } from 'hooks/dialog'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'

interface Props {
  keyField: string
  setter: (val: string) => void
}

const props = defineProps<Props>()

const { t } = useI18n()
const { close } = useDialog()
const { toast } = useToast()

const content = ref<string>()
const showError = ref<boolean>(false)

const saveKeybinding = async () => {
  const value = toValue(content)
  if (!value) {
    showError.value = true
    return
  }

  showError.value = false
  const key = toValue(props.keyField)

  try {
    const encodeValue = value ? btoa(value) : null
    await request('/download/setting', {
      method: 'POST',
      body: JSON.stringify({ key, value: encodeValue }),
    })
    const desString = value ? value.slice(0, 4) + '****' + value.slice(-4) : ''
    props.setter(desString)
    close()
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: (error as Error).message,
      life: 3000,
    })
  }
}
</script>
