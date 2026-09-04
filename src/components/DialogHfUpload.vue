<template>
  <div class="flex h-full flex-col">
    <Tabs v-model="stepValue" class="flex flex-1 flex-col overflow-hidden">
      <TabsList class="grid w-full grid-cols-3">
        <TabsTrigger value="1">{{ $t('selectRepoType') }}</TabsTrigger>
        <TabsTrigger value="2" :disabled="stepValue === '1'">{{ $t('inputRepoInfo') }}</TabsTrigger>
        <TabsTrigger value="3" :disabled="stepValue === '1' || stepValue === '2'">{{ $t('selectFiles') }}</TabsTrigger>
      </TabsList>
      <TabsContent value="1" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col gap-4 px-4">
          <div class="flex flex-wrap gap-4">
            <Button
              v-for="item in repoTypeOptions"
              :key="item.value"
              :variant="repoType === item.value ? 'default' : 'secondary'"
              @click="item.command"
            >
              {{ item.label }}
            </Button>
          </div>
        </div>
      </TabsContent>
      <TabsContent value="2" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col gap-4 px-4">
          <div class="flex flex-col gap-2">
            <label class="text-sm font-medium">{{ $t('repoId') }}</label>
            <Input v-model="repoId" class="w-full" :placeholder="$t('repoIdPlaceholder')" />
          </div>
          <div class="flex flex-col gap-2">
            <label class="text-sm font-medium">{{ $t('revision') }}</label>
            <Input v-model="revision" class="w-full" :placeholder="$t('revisionPlaceholder')" />
          </div>
          <div v-if="repoType === 'model'" class="flex items-center gap-2">
            <Checkbox v-model="privateRepo" id="hf-private-repo" />
            <label for="hf-private-repo" class="text-sm">{{ $t('privateRepo') }}</label>
          </div>
          <div class="flex justify-between pt-4">
            <Button variant="secondary" @click="handleBackRepoType">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
            <Button :disabled="!repoId" @click="handleConfirmRepoInfo">
              {{ $t('next') }}
              <ChevronRight class="size-4" />
            </Button>
          </div>
        </div>
      </TabsContent>
      <TabsContent value="3" class="flex-1 overflow-hidden">
        <div class="flex h-full flex-col overflow-hidden">
          <ResponseScroll class="flex-1">
            <div class="flex flex-col gap-2">
              <div
                v-for="file in fileList"
                :key="file.rfilename"
                class="flex items-center gap-2 rounded-mm-ctl border border-mm-border p-2"
              >
                <Checkbox
                  :model-value="selectedFiles.includes(file.rfilename)"
                  @update:model-value="(checked: boolean) => toggleFile(file.rfilename, checked)"
                />
                <span class="flex-1 text-sm">{{ file.rfilename }}</span>
                <span class="text-xs text-mm-muted-fg">{{ bytesToSize(file.size) }}</span>
              </div>
            </div>
          </ResponseScroll>
          <div class="flex justify-between pt-4">
            <Button variant="secondary" @click="handleBackRepoInfo">
              <ChevronLeft class="size-4" />
              {{ $t('back') }}
            </Button>
            <Button :disabled="selectedFiles.length === 0" @click="handleStartUpload">
              {{ $t('upload') }}
            </Button>
          </div>
        </div>
      </TabsContent>
    </Tabs>

    <div v-if="uploading" class="border-t border-mm-border px-4 py-4">
      <div class="flex flex-col gap-2">
        <div class="flex justify-between text-sm">
          <span>{{ currentFile }}</span>
          <span>{{ uploadProgress }}%</span>
        </div>
        <Progress :model-value="uploadProgress" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { Checkbox } from 'components/ui/checkbox'
import { Input } from 'components/ui/input'
import { Progress } from 'components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from 'components/ui/tabs'
import { useDialog } from 'hooks/dialog'
import { request } from 'hooks/request'
import { useToast } from 'hooks/toast'
import { bytesToSize } from 'utils/common'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const { toast } = useToast()
const { close } = useDialog()

const stepValue = ref('1')

const repoType = ref<'model' | 'dataset'>('model')
const repoTypeOptions = [
  {
    label: t('model'),
    value: 'model' as const,
    command: () => {
      repoType.value = 'model'
      stepValue.value = '2'
    },
  },
  {
    label: t('dataset'),
    value: 'dataset' as const,
    command: () => {
      repoType.value = 'dataset'
      stepValue.value = '2'
    },
  },
]

const repoId = ref('')
const revision = ref('main')
const privateRepo = ref(false)

const handleBackRepoType = () => {
  repoId.value = ''
  revision.value = 'main'
  privateRepo.value = false
  stepValue.value = '1'
}

const handleConfirmRepoInfo = async () => {
  try {
    const result = await request('/hf/upload/files', {
      method: 'POST',
      body: JSON.stringify({
        repoType: repoType.value,
        repoId: repoId.value,
        revision: revision.value,
        private: privateRepo.value,
      }),
    })
    fileList.value = result?.files ?? []
    stepValue.value = '3'
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: (error as Error).message,
      life: 5000,
    })
  }
}

const handleBackRepoInfo = () => {
  fileList.value = []
  selectedFiles.value = []
  stepValue.value = '2'
}

const fileList = ref<Array<{ rfilename: string; size: number }>>([])
const selectedFiles = ref<string[]>([])

const toggleFile = (filename: string, checked: boolean) => {
  if (checked) {
    selectedFiles.value.push(filename)
  } else {
    selectedFiles.value = selectedFiles.value.filter((f) => f !== filename)
  }
}

const uploading = ref(false)
const currentFile = ref('')
const uploadProgress = ref(0)

const handleStartUpload = async () => {
  uploading.value = true
  try {
    for (const file of selectedFiles.value) {
      currentFile.value = file
      uploadProgress.value = 0
      await request('/hf/upload', {
        method: 'POST',
        body: JSON.stringify({
          repoType: repoType.value,
          repoId: repoId.value,
          revision: revision.value,
          file,
        }),
      })
      uploadProgress.value = 100
    }
    toast.add({
      severity: 'success',
      summary: 'Success',
      detail: 'Upload completed',
      life: 3000,
    })
    close()
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: (error as Error).message,
      life: 5000,
    })
  } finally {
    uploading.value = false
  }
}
</script>
