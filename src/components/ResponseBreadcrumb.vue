<template>
  <div ref="container" class="flex items-center gap-1 overflow-hidden text-sm">
    <template v-for="(item, index) in items ?? []" :key="index">
      <button
        v-if="index < (items?.length ?? 0) - 1"
        type="button"
        class="mm-transition flex items-center gap-1 rounded-mm-ctl border-0 bg-transparent px-1 text-mm-muted-fg hover:bg-mm-fg/8 hover:text-mm-accent"
        @click="item.command?.()"
      >
        <!-- the all-fit folder glyph earns its keep at tiny sizes -->
        <img :src="folderGlyph" class="size-3.5 shrink-0" alt="" draggable="false" />
        {{ item.label }}
      </button>
      <span v-else class="flex items-center gap-1 font-medium text-mm-fg">
        <img :src="folderGlyph" class="size-3.5 shrink-0" alt="" draggable="false" />
        {{ item.label }}
      </span>
      <ChevronRight
        v-if="index < (items?.length ?? 0) - 1"
        class="size-4 shrink-0 text-mm-muted-fg"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { ref } from 'vue'
import { type BreadcrumbItem } from 'types/breadcrumb'
import { assetUrl } from 'utils/media'

/** `close-folder_all-fit.svg` reads best at small sizes: breadcrumb glyphs.
 *  Served cached like the rest of the artwork (optimization B-2). */
const folderGlyph = assetUrl('folder-glyph')

interface Props {
  items?: BreadcrumbItem[]
}

defineProps<Props>()

const container = ref<HTMLElement>()
</script>
