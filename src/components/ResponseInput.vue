<template>
  <div
    :class="[
      'mm-transition flex items-center gap-2 rounded-mm-ctl border px-3 py-2',
      'border-mm-fg/12 bg-mm-fg/6 shadow-mm-glass-1 backdrop-blur-md',
      'focus-within:border-mm-accent/60',
    ]"
  >
    <slot name="prefix">
      <component
        :is="resolveIcon(prefixIcon)"
        v-if="prefixIcon && resolveIcon(prefixIcon)"
        class="size-4 text-mm-muted-fg"
      />
    </slot>

    <!--
      Plain controlled input: the DOM element owns the text while the user
      types (including IME composition), and `content` is committed on the
      configured trigger event. The previous implementation layered a second
      `input` listener plus an inner buffer computed on top of v-model; the
      commit handler had no composition guard, so an `input` event fired
      mid-composition read the stale committed value and wrote it back into
      `el.value`, wiping the characters being composed (the field looked
      "unable to type" under a Japanese IME). One listener with an explicit
      composition guard cannot break that way.
    -->
    <input
      ref="inputRef"
      class="min-w-0 flex-1 border-none bg-transparent text-sm text-mm-fg outline-none placeholder:text-mm-muted-fg"
      type="text"
      :value="content ?? ''"
      :placeholder="placeholder"
      spellcheck="false"
      autocomplete="off"
      v-bind="$attrs"
      @input="onInput"
      @change="onChange"
      @compositionstart="composing = true"
      @compositionend="onCompositionEnd"
    />

    <!--
      type="button": this component is rendered inside ModelContent's <form>
      (the network-preview URL input), and a bare <button> defaults to
      type="submit" - clearing the field submitted the form.
    -->
    <button
      v-if="allowClear"
      v-show="content"
      type="button"
      class="mm-transition size-4 border-0 bg-transparent p-0 text-mm-muted-fg hover:scale-110 hover:text-mm-fg"
      @click="clearContent"
    >
      <X class="size-4" />
    </button>

    <slot name="suffix">
      <component
        :is="resolveIcon(suffixIcon)"
        v-if="suffixIcon && resolveIcon(suffixIcon)"
        class="size-4 text-mm-muted-fg"
      />
    </slot>
  </div>
</template>

<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref } from 'vue'
import { resolveIcon } from 'utils/iconMap'

interface Props {
  prefixIcon?: string
  suffixIcon?: string
  placeholder?: string
  allowClear?: boolean
  updateTrigger?: string
  validate?: (value: string | undefined) => boolean
}

const props = defineProps<Props>()
const [content, modifiers] = defineModel<string, 'trim' | 'valid'>()

const inputRef = ref<HTMLInputElement>()
const composing = ref(false)

const trigger = computed(() => props.updateTrigger ?? 'change')

/** Commit the DOM value into the model (trim / validate honoured). */
const commit = () => {
  const el = inputRef.value
  if (!el) return
  let value: string | undefined = el.value
  if (modifiers.trim) {
    value = value?.trim()
  }
  if (modifiers.valid) {
    const isValid = props.validate?.(value) ?? true
    if (!isValid) {
      // Restore the last committed value; the DOM diverged from the model.
      el.value = content.value ?? ''
      return
    }
  }
  content.value = value
  // Only write back when the DOM value actually differs (a trim or a failed
  // validation); rewriting an identical value resets the caret.
  if (el.value !== (value ?? '')) {
    el.value = value ?? ''
  }
}

const onInput = () => {
  // While an IME composition is open the DOM text is provisional; committing
  // it (or rewriting the element) would destroy the composition.
  if (composing.value) return
  if (trigger.value === 'input') commit()
}

const onCompositionEnd = () => {
  composing.value = false
  if (trigger.value === 'input') commit()
}

/** `change`-triggered fields commit on Enter / blur (also post-composition). */
const onChange = () => {
  if (composing.value) return
  if (trigger.value !== 'input') commit()
}

const clearContent = () => {
  content.value = undefined
  if (inputRef.value) {
    inputRef.value.value = ''
    inputRef.value.focus()
  }
}
</script>
