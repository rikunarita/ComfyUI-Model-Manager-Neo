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

    <input
      ref="inputRef"
      v-model="inputValue"
      class="flex-1 border-none bg-transparent text-sm text-mm-fg outline-none placeholder:text-mm-muted-fg"
      type="text"
      :placeholder="placeholder"
      spellcheck="false"
      autocomplete="off"
      v-bind="$attrs"
      @[trigger]="updateContent"
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

const innerValue = ref<string>()
const inputValue = computed({
  get: () => innerValue.value ?? content.value,
  set: val => {
    innerValue.value = val
  },
})

const trigger = computed(() => props.updateTrigger ?? 'change')

const updateContent = () => {
  let value = inputValue.value

  if (modifiers.trim) {
    value = value?.trim()
  }

  if (modifiers.valid) {
    const isValid = props.validate?.(value) ?? true
    if (!isValid) {
      innerValue.value = content.value
      return
    }
  }

  innerValue.value = undefined
  content.value = value
  // Only write back when the DOM value actually differs (e.g. after a failed
  // validation or a trim). Rewriting an identical value resets the caret to the
  // end, which is jarring while typing with update-trigger="input".
  if (inputRef.value && inputRef.value.value !== (value ?? '')) {
    inputRef.value.value = value ?? ''
  }
}

defineOptions({
  inheritAttrs: false,
})

const clearContent = () => {
  content.value = undefined
  inputRef.value?.focus()
}
</script>
