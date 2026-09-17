<script setup lang="ts">
interface Props {
  /** 0-100 task progress; drives the ring arc and the percentage read-out. */
  progress: number
  /** Size of the percentage glyph (the two call sites differ by 1px). */
  percentClass?: string
}
withDefaults(defineProps<Props>(), { percentClass: 'text-[10px]' })
</script>

<template>
  <!--
    Shared ZipNN task ring (folder-batch bar and model-card corner button):
    a circular progress arc with the percentage in the middle. Extracted from
    the two call sites that rendered byte-identical SVG markup.
  -->
  <span class="relative grid size-full place-items-center">
    <svg viewBox="0 0 36 36" class="size-full -rotate-90">
      <circle
        cx="18"
        cy="18"
        r="15"
        fill="none"
        stroke="currentColor"
        stroke-width="4"
        class="text-mm-fg/25"
      />
      <circle
        cx="18"
        cy="18"
        r="15"
        fill="none"
        stroke="currentColor"
        stroke-width="4"
        stroke-linecap="round"
        :stroke-dasharray="`${(progress * 94.25) / 100} 94.25`"
        class="text-mm-accent"
      />
    </svg>
    <span class="absolute leading-none font-bold text-mm-accent tabular-nums" :class="percentClass">
      {{ Math.round(progress) }}%
    </span>
  </span>
</template>
