<template>
  <!--
    The shipped HashReverse artwork (assets/HashReverse-Icon/), inlined
    VERBATIM so its `currentColor` strokes inherit the surrounding text
    colour - an <img> would freeze them to black on the dark theme. The
    wrapper sizes the 24x24 source down to the action-row icon grid.
  -->
  <span class="inline-flex size-4 [&>svg]:size-4" v-html="raw"></span>
</template>

<script setup lang="ts">
import raw from '../../assets/HashReverse-Icon/HashReverse-icon.svg?raw'
</script>
