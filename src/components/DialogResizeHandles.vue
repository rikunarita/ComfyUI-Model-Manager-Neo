<script setup lang="ts">
interface Props {
  allowX: boolean
  allowY: boolean
}
defineProps<Props>()

const emits = defineEmits<{
  /** The parent reads `data-resize-pos` off `event.target`. */
  resize: [event: MouseEvent]
}>()
</script>

<template>
  <!--
    The eight edge/corner grips of a manager window. Pure markup: the parent
    resolves the direction from the handle's `data-resize-pos` attribute.
  -->
  <div data-dialog-resizer>
    <div
      v-if="allowX"
      data-resize-pos="left"
      class="absolute top-0 -left-1 h-full w-2 cursor-ew-resize"
      @mousedown="emits('resize', $event)"
    ></div>
    <div
      v-if="allowX"
      data-resize-pos="right"
      class="absolute top-0 -right-1 h-full w-2 cursor-ew-resize"
      @mousedown="emits('resize', $event)"
    ></div>
    <div
      v-if="allowY"
      data-resize-pos="top"
      class="absolute -top-1 left-0 h-2 w-full cursor-ns-resize"
      @mousedown="emits('resize', $event)"
    ></div>
    <div
      v-if="allowY"
      data-resize-pos="bottom"
      class="absolute -bottom-1 left-0 h-2 w-full cursor-ns-resize"
      @mousedown="emits('resize', $event)"
    ></div>
    <div
      v-if="allowX && allowY"
      data-resize-pos="top-left"
      class="absolute -top-1 -left-1 size-2 cursor-se-resize"
      @mousedown="emits('resize', $event)"
    ></div>
    <div
      v-if="allowX && allowY"
      data-resize-pos="top-right"
      class="absolute -top-1 -right-1 size-2 cursor-sw-resize"
      @mousedown="emits('resize', $event)"
    ></div>
    <div
      v-if="allowX && allowY"
      data-resize-pos="bottom-left"
      class="absolute -bottom-1 -left-1 size-2 cursor-se-resize"
      @mousedown="emits('resize', $event)"
    ></div>
    <div
      v-if="allowX && allowY"
      data-resize-pos="bottom-right"
      class="absolute -right-1 -bottom-1 size-2 cursor-se-resize"
      @mousedown="emits('resize', $event)"
    ></div>
  </div>
</template>
