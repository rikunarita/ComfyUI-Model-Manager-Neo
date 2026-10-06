<template>
  <!--
    The shipped HashReverse artwork (assets/HashReverse-Icon/), inlined
    VERBATIM so its `currentColor` strokes inherit the surrounding text
    colour - an <img> would freeze them to black on the dark theme.
  -->
  <span class="inline-flex size-5" v-html="sized"></span>
</template>

<script setup lang="ts">
import raw from '../../assets/HashReverse-Icon/HashReverse-icon.svg?raw'

/**
 * The artwork root carries no class of its own, and `Button.vue`'s base class
 * forces every descendant svg WITHOUT a `size-*` class down to 16px
 * (`[&_svg:not([class*='size-'])]:size-4`); that selector (class + :not(class)
 * + type) outranks any wrapper rule, so the bare svg rendered a size smaller
 * than its Lucide siblings - they carry an explicit `size-5` and are therefore
 * excluded from the fallback. Tagging the injected root with the same utility
 * class opts it out of the fallback and keeps it on the 20px icon grid.
 */
const sized = raw.replace('<svg ', '<svg class="size-5" ')
</script>
