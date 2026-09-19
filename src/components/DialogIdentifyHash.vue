<template>
  <!--
    Result of the Civitai by-hash lookup ("what IS this file?"): the resolved
    model / version with its preview, base model and trigger words, the
    ready-to-run download command the official CLI prints on a hit, the
    version's file list and every hash notation that was tried.
  -->
  <ResponseScroll class="h-full">
    <div class="flex flex-col gap-4 px-5 pb-5 text-sm">
      <div class="flex items-start gap-3">
        <img
          v-if="match.images?.length"
          :src="match.images[0]"
          alt=""
          class="size-24 shrink-0 rounded-mm-ctl border border-mm-border object-cover"
        />
        <div class="min-w-0 flex-1">
          <div class="truncate font-medium">
            {{ match.modelName ?? '-' }}
            <span class="text-mm-muted-fg">/ {{ match.versionName ?? '-' }}</span>
          </div>
          <div class="mt-1 flex flex-col gap-0.5 text-xs text-mm-muted-fg">
            <span>
              {{ $t('identifyMatchedHash') }}: {{ match.hashType }}
              <span class="font-mono">{{ match.hash }}</span>
            </span>
            <span v-if="match.baseModel">{{ $t('info.baseModel') }}: {{ match.baseModel }}</span>
            <span v-if="match.modelType">{{ $t('modelType') }}: {{ match.modelType }}</span>
          </div>
        </div>
      </div>

      <div v-if="match.trainedWords?.length" class="flex flex-col gap-1">
        <div class="text-xs font-medium">{{ $t('identifyTriggerWords') }}</div>
        <div class="text-xs text-mm-muted-fg">{{ match.trainedWords.join(', ') }}</div>
      </div>

      <div
        v-if="match.downloadCommand"
        class="flex items-center gap-2 rounded-mm-ctl border border-mm-border bg-mm-fg/4 p-2"
      >
        <code class="min-w-0 flex-1 truncate font-mono text-xs" :title="match.downloadCommand">
          {{ match.downloadCommand }}
        </code>
        <Button
          variant="ghost"
          size="icon-xs"
          :title="$t('copyCommand')"
          :aria-label="$t('copyCommand')"
          @click="copyCommand"
        >
          <Copy class="size-3.5" />
        </Button>
      </div>

      <div v-if="match.files?.length" class="flex flex-col gap-1">
        <div class="text-xs font-medium">{{ $t('identifyFiles') }}</div>
        <div
          v-for="file in match.files"
          :key="file.name ?? ''"
          class="flex justify-between gap-2 text-xs text-mm-muted-fg"
        >
          <span class="truncate">{{ file.name }}</span>
          <span class="shrink-0">{{ bytesToSize((file.sizeKB ?? 0) * 1024) }}</span>
        </div>
      </div>

      <div class="flex flex-col gap-1">
        <div class="text-xs font-medium">{{ $t('identifyHashes') }}</div>
        <div
          v-for="(value, key) in hashes"
          :key="key"
          class="flex justify-between gap-2 text-xs text-mm-muted-fg"
        >
          <span class="shrink-0">{{ key }}</span>
          <span class="truncate font-mono" :title="String(value)">{{ value }}</span>
        </div>
      </div>

      <Button
        v-if="match.modelPage"
        variant="secondary"
        class="self-start"
        @click="openExternal(match.modelPage)"
      >
        <ExternalLink class="size-4" />
        {{ $t('openModelPage') }}
      </Button>
    </div>
  </ResponseScroll>
</template>

<script setup lang="ts">
import { Copy, ExternalLink } from '@lucide/vue'
import ResponseScroll from 'components/ResponseScroll.vue'
import { Button } from 'components/ui/button'
import { useToast } from 'hooks/toast'
import { bytesToSize } from 'utils/common'

interface IdentifyFile {
  name?: string | null
  sizeKB?: number | null
  downloadUrl?: string | null
  hashes?: Record<string, string> | null
}

interface IdentifyMatch {
  hash: string
  hashType: string
  versionId?: number | null
  modelId?: number | null
  modelName?: string | null
  modelType?: string | null
  versionName?: string | null
  baseModel?: string | null
  trainedWords?: string[]
  images?: string[]
  files?: IdentifyFile[]
  modelPage?: string | null
  downloadCommand?: string | null
}

interface Props {
  result: { matched: IdentifyMatch; hashes: Record<string, string>; hashedFile: boolean }
}
const props = defineProps<Props>()

const { toast } = useToast()
const match = props.result.matched
const hashes = props.result.hashes ?? {}

const openExternal = (url: string | null) => {
  if (url) window.open(url, '_blank')
}

const copyCommand = async () => {
  if (!match.downloadCommand) return
  try {
    await navigator.clipboard.writeText(match.downloadCommand)
  } catch {
    // Clipboard denied (permissions, non-secure context): show the command
    // itself so it can be copied by hand.
    toast.add({ severity: 'warn', detail: match.downloadCommand, life: 8000 })
  }
}
</script>
