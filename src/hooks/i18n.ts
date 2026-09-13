import { type Composer } from 'vue-i18n'
import { i18n } from '../i18n'

/**
 * Translation helper for module-level (non-component) code.
 *
 * `useI18n()` only resolves inside a component's `setup()`. The websocket
 * listeners in `hooks/hfUpload` are registered at import time — before, and
 * outside of, any component — so they need the global composer instead.
 * `i18n.global` is the very instance the app injects, so the locale stays in
 * sync with whatever ComfyUI reports (and with a later runtime switch).
 */
const composer = i18n.global as Composer

export const useI18nGlobal = () => {
  const t = (key: string, named?: Record<string, unknown>) =>
    named ? composer.t(key, named) : composer.t(key)

  return { t }
}
