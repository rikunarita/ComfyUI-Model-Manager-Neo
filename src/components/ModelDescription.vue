<template>
  <div class="relative">
    <textarea
      v-show="active"
      ref="textareaRef"
      v-model="innerValue"
      :class="[
        'w-full resize-none overflow-hidden bg-mm-fg/4 px-3 py-2 backdrop-blur-sm outline-none',
        'rounded-lg border',
        /*
         * BUG FIX: `--p-form-field-border-color` /
         * `--p-form-field-focus-border-color` are PrimeVue theme variables.
         * PrimeVue was removed from this fork and nothing defines them, so the
         * declarations were invalid at computed-value time and the description
         * textarea rendered with NO border and NO focus indication. Mapped to
         * the Neo `--mm-*` tokens the rest of the UI uses.
         */
        'border-mm-border',
        'focus:border-mm-accent',
        'relative z-10',
      ]"
      @input="resizeTextarea"
      @blur="exitEditMode"
    ></textarea>

    <div v-show="!active">
      <div v-show="editable" class="mb-4 flex items-center gap-2 text-mm-muted-fg">
        <!-- BUG FIX: `pi pi-info-circle` rendered empty (PrimeIcons removed). -->
        <Info class="size-4 shrink-0" />
        <span>
          {{ $t('tapToChange') }}
        </span>
      </div>

      <div class="relative">
        <div
          v-if="renderedDescription"
          :class="$style['markdown-body']"
          v-html="renderedDescription"
        ></div>
        <div v-else class="flex flex-col items-center gap-2 py-5">
          <!-- BUG FIX: `pi pi-info-circle` rendered empty (PrimeIcons removed). -->
          <Info class="size-5 opacity-60" />
          <div>no description</div>
        </div>
        <div
          v-show="editable"
          class="absolute top-0 left-0 size-full cursor-pointer"
          @click="entryEditMode"
        ></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Info } from '@lucide/vue'
import { nextTick, ref, watch } from 'vue'
import { useModelDescription } from 'hooks/model'

const editable = defineModel<boolean>('editable')
const active = ref(false)

const { description, renderedDescription } = useModelDescription()

const textareaRef = ref<HTMLTextAreaElement>()
const innerValue = ref<string>()

watch(
  description,
  value => {
    innerValue.value = value
  },
  { immediate: true },
)

const resizeTextarea = () => {
  const textarea = textareaRef.value!

  textarea.style.height = 'auto'
  const scrollHeight = textarea.scrollHeight

  textarea.style.height = scrollHeight + 'px'

  textarea.scrollIntoView({
    block: 'nearest',
    inline: 'nearest',
  })
}

const entryEditMode = async () => {
  active.value = true
  await nextTick()
  resizeTextarea()
  textareaRef.value!.focus()
}

const exitEditMode = () => {
  description.value = innerValue.value!
  active.value = false
}
</script>

<style lang="less" module>
.markdown-body {
  /*
   * BUG FIX: Tailwind v4 no longer resolves the LESS-time `theme()` helper
   * inside SFC module styles — the literal string `theme("fontFamily.sans")`
   * ended up in the built CSS and the declarations were dropped as invalid.
   * The resolved default-theme values are inlined instead (identical to what
   * Tailwind v3 emitted for these keys).
   */
  font-family:
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    Roboto,
    'Helvetica Neue',
    Arial,
    'Noto Sans',
    sans-serif,
    'Apple Color Emoji',
    'Segoe UI Emoji',
    'Segoe UI Symbol',
    'Noto Color Emoji';
  font-size: 1rem;
  line-height: 1.625;
  word-break: break-word;
  margin: 0;

  &::before {
    display: table;
    content: '';
  }

  &::after {
    display: table;
    content: '';
    clear: both;
  }

  > *:first-child {
    margin-top: 0 !important;
  }

  > *:last-child {
    margin-bottom: 0 !important;
  }

  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    margin-top: 1.5em;
    margin-bottom: 1em;
    font-weight: 600;
    line-height: 1.25;
  }

  h1 {
    font-size: 2em;
    padding-bottom: 0.3em;
    border-bottom: 1px solid var(--mm-border);
  }

  h2 {
    font-size: 1.5em;
    padding-bottom: 0.3em;
    border-bottom: 1px solid var(--mm-border);
  }

  h3 {
    font-size: 1.25em;
  }

  h4 {
    font-size: 1em;
  }

  h5 {
    font-size: 0.875em;
  }

  h6 {
    font-size: 0.85em;
    color: var(--mm-muted-fg);
  }

  a {
    color: #1e8bc3;
    text-decoration: none;
    word-break: break-all;
  }

  a:hover {
    text-decoration: underline;
  }

  p,
  blockquote,
  ul,
  ol,
  dl,
  table,
  pre,
  details {
    margin-top: 0;
    margin-bottom: 1em;
  }

  p img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  ul,
  ol {
    padding-left: 2em;
  }

  li {
    margin: 0.5em 0;
  }

  blockquote {
    padding: 0px 1em;
    border-left: 0.25em solid var(--mm-muted-fg);
    color: var(--mm-muted-fg);
    margin: 1em 0;
  }

  blockquote > *:first-child {
    margin-top: 0;
  }

  blockquote > *:last-child {
    margin-bottom: 0;
  }

  pre {
    font-size: 85%;
    border-radius: 6px;
    padding: 8px 16px;
    overflow-x: auto;
    background: color-mix(in oklab, var(--mm-fg) 7%, transparent);
    border: 1px solid var(--mm-border);
  }

  pre code,
  pre tt {
    display: inline;
    padding: 0;
    margin: 0;
    overflow: visible;
    line-height: inherit;
    word-wrap: normal;
    background-color: transparent;
    border: 0;
  }
}
</style>
