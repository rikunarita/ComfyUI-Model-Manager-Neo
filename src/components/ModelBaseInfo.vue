<template>
  <div class="flex flex-col gap-4">
    <div v-if="editable" class="flex flex-col gap-4">
      <ResponseSelect v-model="type" class="w-full" :items="typeOptions">
        <template #prefix>
          <span>{{ $t('modelType') }}</span>
        </template>
      </ResponseSelect>

      <div class="flex gap-2 overflow-hidden">
        <div
          class="flex-1 overflow-hidden rounded-mm-ctl border border-mm-fg/10 bg-mm-fg/8 backdrop-blur-sm"
        >
          <div class="flex h-full items-center justify-end">
            <span v-if="renderedModelFolder" class="truncate px-2">
              {{ renderedModelFolder }}
            </span>
            <span v-else class="px-2 text-sm text-mm-muted-fg italic">
              {{ $t('selectModelTypeFirst') }}
            </span>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          :disabled="!type"
          :title="$t('selectFolder')"
          :aria-label="$t('selectFolder')"
          @click="handleSelectFolder"
        >
          <FolderOpen class="size-4" />
        </Button>

        <!-- Folder select dialog (reka-ui Dialog) -->
        <Dialog :open="folderSelectVisible" @update:open="folderSelectVisible = $event">
          <DialogContent class="flex max-h-[50vh] max-w-[50vw] flex-col">
            <DialogHeader>
              <DialogTitle>{{ $t('folder') }}</DialogTitle>
            </DialogHeader>
            <div class="flex flex-1 flex-col overflow-hidden">
              <div class="flex-1 overflow-hidden">
                <ResponseScroll>
                  <Tree
                    v-model="selectedFolderItem"
                    :items="pathOptions"
                    :get-key="(item: any) => item.key ?? ''"
                    :get-children="(item: any) => item.children"
                    class="h-full"
                  />
                </ResponseScroll>
              </div>
              <div class="flex justify-end gap-2 pt-4">
                <Button variant="secondary" @click="handleCancelSelectFolder">
                  {{ $t('cancel') }}
                </Button>
                <Button @click="handleConfirmSelectFolder">
                  {{ $t('select') }}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <ResponseInput
        v-model.trim.valid="basename"
        class="-mr-2 text-right"
        update-trigger="blur"
        :placeholder="$t('modelNamePlaceholder')"
        :validate="validateBasename"
      >
        <template #suffix>
          <span class="text-base opacity-60">
            {{ extension }}
          </span>
        </template>
      </ResponseInput>
      <div class="-mt-2 text-right text-xs text-mm-muted-fg">
        {{ $t('modelNameHint') }}
      </div>
    </div>

    <!--
      Auto horizontal ratio: the label column shrink-wraps to its longest
      (never-wrapping) label - which differs per locale, e.g. Japanese labels
      are wider than English - while the value column takes the remainder.
      `table-fixed` + a hard-coded `w-32` label column used to overflow the
      translated labels into the value column ("table is broken").
    -->
    <table class="w-full border-collapse border border-mm-border">
      <colgroup>
        <col class="w-[1%]" />
        <col />
      </colgroup>
      <tbody>
        <tr
          v-for="item in information"
          :key="item.key"
          class="h-8 border-b border-mm-border whitespace-nowrap"
        >
          <td class="border-r border-mm-border bg-mm-fg/6 px-4 backdrop-blur-sm">
            {{ $t(`info.${item.key}`) }}
          </td>
          <td class="overflow-hidden px-4 break-all text-ellipsis">
            <Tooltip :delay-duration="800">
              <TooltipTrigger as-child>
                <span>{{ item.display }}</span>
              </TooltipTrigger>
              <TooltipContent
                v-if="!['pathIndex', 'basename'].includes(item.key)"
                side="top"
                class="max-w-lg"
              >
                {{ item.display }}
              </TooltipContent>
            </Tooltip>
          </td>
        </tr>
      </tbody>
    </table>

    <!--
      Duplicate-model warning: another file in the library carries the same
      SHA256 recorded in the notes front-matter (no hashing pass needed).
    -->
    <div
      v-if="duplicates.length"
      class="flex items-center gap-2 rounded-mm-ctl border border-mm-danger/40 bg-mm-danger/15 px-3 py-2 text-sm text-mm-danger"
    >
      <CircleAlert class="size-4 shrink-0" />
      <span class="break-all">{{ $t('duplicateModels', { paths: duplicates.join(', ') }) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CircleAlert, FolderOpen } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ResponseInput from 'components/ResponseInput.vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import ResponseSelect from 'components/ResponseSelect.vue'
import { Button } from 'components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from 'components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from 'components/ui/tooltip'
import { Tree } from 'components/ui/tree'
import { useModelBaseInfo, useModelFolder, useModels } from 'hooks/model'
import { useToast } from 'hooks/toast'
import { type Model } from 'types/typings'
import { genModelKey } from 'utils/model'

const editable = defineModel<boolean>('editable')

const { t } = useI18n()
const { toast } = useToast()

const { baseInfo, pathIndex, subFolder, basename, extension, type, modelFolders, model } =
  useModelBaseInfo()
const { data: allModels, getFullPath } = useModels()

/** Other files sharing this model's recorded SHA256 (exact duplicates). */
const duplicates = computed(() => {
  const sha = (model.value as Model).modelSha256
  if (!sha) return []
  const paths: string[] = []
  for (const list of Object.values(allModels.value)) {
    for (const m of list) {
      if (!m.isFolder && m.modelSha256 === sha && genModelKey(m) !== genModelKey(model.value)) {
        paths.push(getFullPath(m))
      }
    }
  }
  return paths
})

/**
 * Absolute directory of the model, WITHOUT the trailing separator the Directory
 * row renders. The folder Tree keys its nodes on plain paths (see
 * `useModelFolder`), so pre-selecting the current folder has to use this and
 * not `baseInfo.pathIndex.display`.
 */
const folderKey = computed(() => {
  const folders = modelFolders.value[type.value] ?? []
  const folderPath = folders[pathIndex.value]
  if (!folderPath) return undefined
  return [folderPath, subFolder.value].filter(Boolean).join('/')
})

watch(type, () => {
  subFolder.value = ''
})

// BUG FIX (removed): a `watch(editable, …, { immediate: true })` used to reset
// `type.value = ''` whenever the editor became editable. Upstream never did
// this, and it was destructive:
//  - in the model-detail editor the model's own type was thrown away, so
//    saving a move/rename sent `type: ""` and the backend rejected it with
//    "PathIndex 0 is not in " (the type root could not be resolved);
//  - in the Create Download Task dialog (always `editable`) the type resolved
//    from the Civitai/Hugging Face search was wiped, forcing a manual pick.
// `type` is part of the form data cloned from the model and must survive
// entering edit mode; the user can still change it via the selector below.

const typeOptions = computed(() => {
  return Object.keys(modelFolders.value).map(curr => {
    return {
      value: curr,
      label: curr,
      command: () => {
        type.value = curr
        pathIndex.value = 0
      },
    }
  })
})

const information = computed(() => {
  return Object.values(baseInfo.value).filter(row => {
    if (editable.value) {
      const hiddenKeys = ['basename', 'pathIndex']
      return !hiddenKeys.includes(row.key)
    }
    return true
  })
})

/**
 * Validate the file-name field.
 *
 * FEATURE FIX: `/` used to be rejected together with the characters that are
 * genuinely illegal in a file name, so typing "sub/model.safetensors" was
 * silently reverted and a model could never be filed into a sub-folder from the
 * editor. `/` is a path separator now; the backend already traversal-checks the
 * resulting path (`utils.get_full_path`) and creates missing directories
 * (`utils.rename_model`), and the empty / `.` / `..` segment check below keeps
 * the client side just as strict.
 */
const validateBasename = (val: string | undefined) => {
  const fail = (detail: string) => {
    toast.add({ severity: 'error', detail, life: 3000 })
    return false
  }
  if (!val) {
    return fail(t('validation.nameRequired'))
  }
  // `\ : * ? " < > |` are illegal in a file name on Windows/SMB shares and are
  // never meaningful here. `/` is deliberately NOT in this set any more.
  if (/[\\:*?"<>|]/.test(val)) {
    return fail(t('validation.nameInvalidChars'))
  }
  const segments = val.split('/')
  if (segments.some(segment => segment === '' || segment === '.' || segment === '..')) {
    return fail(t('validation.nameInvalidPath'))
  }
  return true
}

const folderSelectVisible = ref(false)

const handleSelectFolder = () => {
  if (!type.value) {
    toast.add({
      severity: 'error',
      summary: t('error'),
      detail: t('selectModelTypeFirst'),
      life: 5000,
    })
    return
  }
  folderSelectVisible.value = true
}

const { pathOptions } = useModelFolder({ type })

const selectedModelFolder = ref<string>()

const selectedFolderItem = computed({
  get: () => {
    const selectedKey = selectedModelFolder.value ?? folderKey.value
    return selectedKey ? { key: selectedKey } : undefined
  },
  set: (val: any) => {
    const folderPath = val?.key
    selectedModelFolder.value = folderPath
  },
})

const renderedModelFolder = computed(() => {
  return baseInfo.value.pathIndex?.display
})

const handleCancelSelectFolder = () => {
  selectedModelFolder.value = undefined
  folderSelectVisible.value = false
}

const handleConfirmSelectFolder = () => {
  const folderPath = selectedFolderItem.value?.key

  const folders = modelFolders.value[type.value]
  const idx = folders.findIndex(item => folderPath?.includes(item))
  if (idx < 0) {
    toast.add({
      severity: 'error',
      detail: t('folderNotFound'),
      life: 3000,
    })
    return
  }
  const prefixPath = folders[idx]
  subFolder.value = folderPath!.replace(prefixPath, '')
  if (subFolder.value.startsWith('/')) {
    subFolder.value = subFolder.value.replace('/', '')
  }
  pathIndex.value = idx

  selectedModelFolder.value = undefined
  folderSelectVisible.value = false
}
</script>
