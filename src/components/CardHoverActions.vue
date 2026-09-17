<script setup lang="ts">
import { Copy, ExternalLink, Plus, Workflow } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from 'components/ui/button'
import { useConfig } from 'hooks/config'
import { useModelNodeAction } from 'hooks/model'
import { type Model } from 'types/typings'
import { platformBackgroundStyle, platformLogo } from 'utils/media'

const { model } = defineProps<{ model: Model }>()

const { t } = useI18n()
const { cardSize } = useConfig()
const { addModelNode, copyModelNode, loadPreviewWorkflow, openModelPage } = useModelNodeAction()

/**
 * The hover column only makes sense while the card is large enough to show
 * its caption - the exact same rule ModelCard uses, so every view agrees.
 */
const showActions = computed(() => cardSize.value.width > 120 && cardSize.value.height > 160)
</script>

<template>
  <!--
    Shared hover action column (add node / copy node / preview workflow /
    open model page). Both the flat view and the folder view render model
    cards through this component, so the two views can never drift apart
    functionally again.

    BUG FIX heritage: the wrapper is `pointer-events-none` (so the invisible
    buttons never swallow card clicks) while the inner column turns pointer
    events back on exactly while the card is hovered.
  -->
  <div
    v-show="showActions"
    class="pointer-events-none absolute top-16 right-2 opacity-0 duration-300 group-hover/card:pointer-events-auto group-hover/card:opacity-100 group-data-[dragging=true]/card:pointer-events-none! group-data-[dragging=true]/card:opacity-0!"
  >
    <div class="flex flex-col gap-2">
      <Button
        variant="secondary"
        size="icon-sm"
        class="rounded-full"
        :title="t('addNode')"
        :aria-label="t('addNode')"
        @click.stop="addModelNode(model)"
      >
        <Plus class="size-4" />
      </Button>
      <Button
        variant="secondary"
        size="icon-sm"
        class="rounded-full"
        :title="t('copyNode')"
        :aria-label="t('copyNode')"
        @click.stop="copyModelNode(model)"
      >
        <Copy class="size-4" />
      </Button>
      <Button
        v-show="model.preview"
        variant="secondary"
        size="icon-sm"
        class="rounded-full"
        :title="t('loadWorkflow')"
        :aria-label="t('loadWorkflow')"
        @click.stop="loadPreviewWorkflow(model)"
      >
        <Workflow class="size-4" />
      </Button>
      <Button
        variant="secondary"
        size="icon-sm"
        class="rounded-full"
        :class="platformLogo(model.modelPlatform) && 'border-transparent text-white'"
        :style="platformBackgroundStyle(model.modelPlatform)"
        :title="t('openModelPage')"
        :aria-label="t('openModelPage')"
        @click.stop="openModelPage(model)"
      >
        <ExternalLink class="size-4" />
      </Button>
    </div>
  </div>
</template>
