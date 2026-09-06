<template>
  <div
    :class="[
      'flex items-center gap-2 rounded-mm-ctl border px-3 py-2 mm-transition',
      'border-mm-border-strong bg-mm-surface shadow-mm-1',
      'focus-within:border-mm-border-strong',
    ]"
  >
    <slot name="prefix">
      <component
        v-if="prefixIcon && resolveIcon(prefixIcon)"
        :is="resolveIcon(prefixIcon)"
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

    <button
      v-if="allowClear"
      v-show="content"
      class="mm-transition size-4 border-0 bg-transparent p-0 text-mm-muted-fg hover:text-mm-fg hover:scale-110"
      @click="clearContent"
    >
      <X class="size-4" />
    </button>
    
    <slot name="suffix">
      <component
        v-if="suffixIcon && resolveIcon(suffixIcon)"
        :is="resolveIcon(suffixIcon)"
        class="size-4 text-mm-muted-fg"
      />
    </slot>
  </div>
</template>

<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref } from 'vue'

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
  set: (val) => {
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
  if (inputRef.value) {
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
